"""Ajanın karar katmanı testleri — tarayıcı VEYA AWS gerekmez.

`call_model` sahte bir fonksiyonla değiştirilir; böylece ajanın ekranı
görüp karar verme mantığı gerçek bir model çağrısı yapılmadan test edilir.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from schemas.tour_models import TourElement
from services.tour_agent_service import (
    AgentContext,
    annotate_screenshot,
    build_user_prompt,
    decide_next_step,
    load_agent_system_prompt,
    summarize_decision,
)
from services.tour_dom_inspector import build_inventory, format_inventory_for_model

INVENTORY = [
    TourElement(index=1, role="button", name="İki Modelle Journey Üret", key="c1_generate", x=10, y=10, width=200, height=40),
    TourElement(index=2, role="tab", name="Bilgi Tabanı", x=10, y=60, width=120, height=30),
]


@dataclass
class FakeCallResult:
    raw_text: Optional[str]
    parsed_json: Optional[dict]
    api_call_success: bool = True
    error: Optional[str] = None
    latency_ms: Optional[float] = 120.0
    estimated_cost_usd: Optional[float] = 0.0002
    input_tokens: Optional[int] = 900
    output_tokens: Optional[int] = 60
    total_tokens: Optional[int] = 960


def _fake_call(parsed_json, **overrides):
    """parsed_json döndüren sahte bir call_model üretir."""

    def _call(model_id, system_prompt, user_prompt, temperature, max_tokens, **kwargs):
        _call.last = {
            "model_id": model_id,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "kwargs": kwargs,
        }
        return FakeCallResult(raw_text="{}", parsed_json=parsed_json, **overrides)

    _call.last = None
    return _call


def _context(**overrides):
    data = {"module_title": "C1 — Otomatik Journey Oluşturma", "language": "tr", "max_steps": 10}
    data.update(overrides)
    return AgentContext(**data)


def test_valid_decision_is_returned_with_resolved_element():
    call = _fake_call(
        {"action": "click", "element_index": 1, "narration": "Journey üretimini başlatıyorum."}
    )
    result = decide_next_step(call, "google.gemma-4-31b", _context(), INVENTORY, b"png", 1)
    assert result.valid is True
    assert result.decision.action == "click"
    assert result.element.name == "İki Modelle Journey Üret"


def test_screenshot_is_sent_to_the_model_as_image():
    # Ajanın "canlı sürmesi" ekranı GERÇEKTEN görmesine bağlı; görüntü
    # gönderilmezse bu bir metin-tabanlı senaryo yazarına dönüşürdü.
    call = _fake_call({"action": "wait", "narration": "Sonucu bekliyorum."})
    decide_next_step(call, "google.gemma-4-31b", _context(), INVENTORY, b"fake-png-bytes", 1)
    assert "image_bytes" in call.last["kwargs"]
    assert call.last["kwargs"]["image_bytes"]
    assert call.last["kwargs"]["image_mime_type"] == "image/png"


def test_hallucinated_element_marks_decision_invalid():
    call = _fake_call({"action": "click", "element_index": 42, "narration": "Olmayan öğeye tıklıyorum."})
    result = decide_next_step(call, "google.gemma-4-31b", _context(), INVENTORY, b"png", 1)
    assert result.valid is False
    assert result.decision is not None  # model çıktısı GİZLENMEZ
    assert any("böyle bir öğe yok" in error for error in result.errors)


def test_unparsable_model_output_is_reported():
    call = _fake_call(None, api_call_success=False, error="JSON ayrıştırılamadı")
    result = decide_next_step(call, "google.gemma-4-31b", _context(), INVENTORY, b"png", 1)
    assert result.valid is False
    assert result.decision is None
    assert result.errors


def test_schema_violation_is_reported_not_raised():
    call = _fake_call({"action": "hack_the_browser", "narration": "…"})
    result = decide_next_step(call, "google.gemma-4-31b", _context(), INVENTORY, b"png", 1)
    assert result.valid is False
    assert any("şeması geçersiz" in error for error in result.errors)


def test_context_remembers_history_and_signatures():
    context = _context()
    call = _fake_call({"action": "click", "element_index": 1, "narration": "Butona basıyorum."})
    result = decide_next_step(call, "m", context, INVENTORY, b"png", 1)
    context.remember(result.decision, result.element, result.signature)
    # İmza konumsal indeksle DEĞİL, öğe kimliğiyle (Streamlit key'i) kurulur.
    assert context.signatures == ["click:c1_generate"]
    assert "İki Modelle Journey Üret" in context.history_text()


def test_history_text_is_bounded_to_recent_steps():
    context = _context()
    for index in range(20):
        context.history.append(f"{index}. adım")
    assert len(context.history_text().splitlines()) <= 8


def test_user_prompt_contains_live_inventory_and_history():
    context = _context()
    prompt = build_user_prompt(context, INVENTORY, step_index=1)
    assert "İki Modelle Journey Üret" in prompt
    assert "C1 — Otomatik Journey Oluşturma" in prompt
    assert "ADIM: 1" in prompt


def test_user_prompt_is_english_for_english_tours():
    prompt = build_user_prompt(_context(language="en"), INVENTORY, step_index=2)
    assert "STEP: 2" in prompt
    assert "INTERACTIVE ELEMENTS" in prompt


def test_system_prompt_differs_per_language():
    tr = load_agent_system_prompt("tr")
    en = load_agent_system_prompt("en")
    assert "TÜRKÇE" in tr
    assert "ENGLISH" in en
    for prompt in (tr, en):
        assert "element_index" in prompt


def test_annotate_screenshot_returns_original_on_invalid_image():
    # Bozuk görüntü ajanı durdurmamalı; rozet basılamasa da tur sürer.
    assert annotate_screenshot(b"not-an-image", INVENTORY) == b"not-an-image"


def test_annotate_screenshot_produces_a_different_png_for_valid_image():
    pytest_image = _tiny_png()
    annotated = annotate_screenshot(pytest_image, INVENTORY)
    assert annotated != pytest_image
    assert annotated.startswith(b"\x89PNG")


def _tiny_png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (400, 300), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_build_inventory_numbers_elements_from_one():
    raw = [
        {"role": "button", "name": "A", "x": 0, "y": 0, "width": 10, "height": 10},
        {"role": "button", "name": "B", "x": 0, "y": 20, "width": 10, "height": 10},
    ]
    inventory = build_inventory(raw)
    assert [element.index for element in inventory] == [1, 2]
    assert inventory[1].name == "B"


def test_format_inventory_handles_empty_screen():
    assert "bulunamadı" in format_inventory_for_model([])


def test_summarize_decision_keeps_model_reasoning():
    call = _fake_call(
        {
            "action": "click",
            "element_index": 1,
            "narration": "Üretimi başlatıyorum.",
            "reason": "Ana eylem bu.",
        }
    )
    result = decide_next_step(call, "m", _context(), INVENTORY, b"png", 1)
    summary = summarize_decision(result.decision, result.element)
    assert summary["reason"] == "Ana eylem bu."
    assert summary["element_name"] == "İki Modelle Journey Üret"
