"""A1 AI Görsel Analiz Modu'nun sayfa düzeyindeki (Streamlit AppTest) davranışını,
gerçek Bedrock çağrısı yapmadan (services.a1_vision_service.call_model /
services.bedrock_client.call_model sahtelenerek) test eder.

Odak noktası: Güvenli Kurumsal Mod'da ekran görüntüsü baytlarının hiçbir
modele gönderilmediğinin, AI Görsel Analiz Modu'nda gizlilik onayı
zorunluluğunun ve tek/çok ekranlı görsel analiz iş akışının doğrulanması.
"""
from __future__ import annotations

import copy
import io

from PIL import Image
from streamlit.testing.v1 import AppTest

from services.bedrock_client import ModelCallResult
from services.evaluation_logger import log_evaluation as real_log_evaluation

VALID_VISION_JSON_TEMPLATE = {
    "scene_title": "Ana panele genel bakış",
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "primary_target": "Yeni Yolculuk Ekle butonu",
    "action_type": "click",
    "instruction_text": "Yeni Yolculuk Ekle butonuna tıklayın.",
    "narration": "Ana paneldeki Yolculuk kartında bulunan Yeni Yolculuk Ekle butonuna tıklayın.",
    "on_screen_text": "Yeni Yolculuk Ekle",
    "highlight_description": "Yolculuk kartındaki pembe buton",
    "highlight_rect": {"x": 0.69, "y": 0.46, "width": 0.16, "height": 0.08},
    "confidence": 0.88,
    "requires_review": True,
}

# Faz 4B: iki aşamalı (görsel gözlem + grounded) akış için ayrı şablonlar.
VALID_OBSERVATION_JSON_TEMPLATE = {
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "detected_visible_labels": ["Yeni Yolculuk Ekle"],
    "possible_primary_target": "Yeni Yolculuk Ekle",
    "preliminary_action_type": "click",
    "preliminary_highlight_rect": {"x": 0.69, "y": 0.46, "width": 0.16, "height": 0.08},
    "confidence": 0.88,
    "visual_uncertainties": [],
}

VALID_GROUNDED_JSON_TEMPLATE = {
    "matched_screen_id": "dashboard",
    "matched_screen_name": "Ana Sayfa",
    "screen_match_score": 0.9,
    "scene_title": "Ana panele genel bakış",
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "primary_target": "Yeni Yolculuk Ekle",
    "target_element_id": "dashboard_new_journey_button",
    "action_type": "click",
    "instruction_text": "Yeni Yolculuk Ekle butonuna tıklayın.",
    "narration": "Ana paneldeki Yeni Yolculuk Ekle butonuna tıklayın.",
    "on_screen_text": "Yeni Yolculuk Ekle",
    "highlight_description": "Yolculuk kartındaki buton",
    "highlight_rect": {"x": 0.69, "y": 0.46, "width": 0.16, "height": 0.08},
    "confidence": 0.9,
    "requires_review": True,
    "grounding_source_ids": ["screen:dashboard", "element:dashboard_new_journey_button"],
    "grounding_warnings": [],
}

VALID_STORYBOARD_JSON = {
    "title": "Test",
    "target_audience": "Trainer",
    "tone": "Kurumsal",
    "scenes": [
        {
            "scene_number": 1,
            "image_id": "screen_01",
            "scene_title": "S1",
            "duration_seconds": 5,
            "narration": "N1",
            "on_screen_text": "T1",
            "transition": "cut",
            "zoom_enabled": True,
            "highlight_description": "H1",
            "requires_review": False,
        }
    ],
    "total_duration_seconds": 5,
    "closing_text": "Kapanış",
}


def _png_bytes(w=200, h=100, color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _patch_log_evaluation_to_tmp(monkeypatch, tmp_path):
    csv_path = tmp_path / "evaluations.csv"

    def fake_log_evaluation(*args, **kwargs):
        kwargs["csv_path"] = csv_path
        return real_log_evaluation(*args, **kwargs)

    monkeypatch.setattr("services.evaluation_logger.log_evaluation", fake_log_evaluation)
    return csv_path


def _seed_project(at: AppTest, screen_ids, note="Bir not.") -> None:
    screens = [
        {
            "image_id": image_id,
            "original_file_name": f"{image_id}.png",
            "scene_label": f"Ekran {i + 1}",
            "note": note,
            "order": i + 1,
            "width": 400,
            "height": 300,
        }
        for i, image_id in enumerate(screen_ids)
    ]
    at.session_state["a1_screens"] = screens
    at.session_state["a1_screen_bytes"] = {image_id: _png_bytes() for image_id in screen_ids}
    at.session_state["a1_export"] = {
        "title": "Test Projesi",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "working_mode": "safe",
        "screens": screens,
    }


def test_safe_mode_never_sends_image_bytes(monkeypatch, tmp_path):
    """Güvenli Kurumsal Mod'da storyboard üretimi ekran görüntüsü baytı GÖNDERMEMELİ."""
    call_log = []

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        call_log.append(image_bytes)
        return ModelCallResult(
            model_id=model_id,
            raw_text="{...}",
            parsed_json=copy.deepcopy(VALID_STORYBOARD_JSON),
            success=True,
            api_call_success=True,
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
            latency_ms=100.0,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A1_MODEL_A", "test-model-a")
    monkeypatch.setenv("A1_MODEL_B", "test-model-b")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    # Storyboard üretimi services/a1_storyboard_service.py içinde import
    # edilen call_model adını kullanır; bu isim modül import edildiği anda
    # bağlandığı için services.bedrock_client.call_model'i değil, doğrudan
    # tüketen modüldeki adı yamalamak gerekir.
    monkeypatch.setattr("services.a1_storyboard_service.call_model", fake_call_model)
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    _seed_project(at, ["screen_01"])
    at.run(timeout=15)
    assert at.exception == []

    # Varsayılan mod Güvenli Kurumsal Mod olmalı.
    assert at.session_state["a1_workflow_mode"] == "safe"

    gen_btn = next(b for b in at.get("button") if b.key == "a1_storyboard_generate")
    gen_btn.click().run(timeout=15)

    assert at.exception == []
    assert len(call_log) == 2  # Plan A + Plan B
    assert all(image_bytes is None for image_bytes in call_log)


def test_vision_mode_requires_privacy_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A1_VISION_MODEL_A", "test-vision-model-a")
    monkeypatch.setenv("A1_VISION_MODEL_B", "test-vision-model-b")
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    _seed_project(at, ["screen_01"])

    mode_radio = next(r for r in at.get("radio") if r.key == "a1_workflow_mode_radio")
    mode_radio.set_value("AI Görsel Analiz Modu")
    at.run(timeout=15)
    assert at.session_state["a1_workflow_mode"] == "vision"

    gen_btn = next(b for b in at.get("button") if b.key == "a1_vision_generate")
    assert gen_btn.disabled is True  # onay kutusu işaretlenmeden buton etkin olmamalı

    privacy_checkbox = next(c for c in at.get("checkbox") if c.key == "a1_vision_privacy_confirmed")
    privacy_checkbox.check()
    at.run(timeout=15)

    gen_btn = next(b for b in at.get("button") if b.key == "a1_vision_generate")
    assert gen_btn.disabled is False


def _run_vision_generation(monkeypatch, tmp_path, screen_ids):
    call_log = []

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        call_log.append({"model_id": model_id, "image_bytes_sent": image_bytes is not None})
        # Faz 4B: aynı sahte call_model, Aşama 1 (görsel gözlem) ve Aşama 2
        # (grounded) çağrılarının her ikisi için de kullanılır; hangi aşamada
        # olduğumuzu build_grounded_user_prompt'un ürettiği benzersiz
        # "GROUNDING VERİSİ" başlığından ayırt ederiz.
        is_grounded_stage = "GROUNDING VERİSİ" in user_prompt
        template = VALID_GROUNDED_JSON_TEMPLATE if is_grounded_stage else VALID_OBSERVATION_JSON_TEMPLATE
        data = copy.deepcopy(template)
        # image_id'yi prompt içindeki bağlamdan çıkarmak yerine basitçe her
        # zaman doğru sırayla eşleşmesi için user_prompt'ta geçen image_id'yi kullan.
        for image_id in screen_ids:
            if f'"image_id": "{image_id}"' in user_prompt:
                data["image_id"] = image_id
                break
        return ModelCallResult(
            model_id=model_id,
            raw_text="{...}",
            parsed_json=data,
            success=True,
            api_call_success=True,
            input_tokens=200,
            output_tokens=150,
            total_tokens=350,
            latency_ms=800.0,
            estimated_cost_usd=0.001,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A1_VISION_MODEL_A", "test-vision-model-a")
    monkeypatch.setenv("A1_VISION_MODEL_B", "test-vision-model-b")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    # services/a1_vision_service.py kendi ad alanına import ettiği call_model
    # adını kullanır; bu yüzden services.bedrock_client.call_model yerine
    # doğrudan tüketen modüldeki adı yamalamak gerekir (aksi halde a1_vision_
    # service başka bir testte zaten import edilmişse yama etkisiz kalır).
    monkeypatch.setattr("services.a1_vision_service.call_model", fake_call_model)
    csv_path = _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    _seed_project(at, screen_ids)

    mode_radio = next(r for r in at.get("radio") if r.key == "a1_workflow_mode_radio")
    mode_radio.set_value("AI Görsel Analiz Modu")
    at.run(timeout=15)

    privacy_checkbox = next(c for c in at.get("checkbox") if c.key == "a1_vision_privacy_confirmed")
    privacy_checkbox.check()
    at.run(timeout=15)

    gen_btn = next(b for b in at.get("button") if b.key == "a1_vision_generate")
    gen_btn.click().run(timeout=30)

    return at, call_log, csv_path


def test_one_screen_vision_workflow(monkeypatch, tmp_path):
    at, call_log, _ = _run_vision_generation(monkeypatch, tmp_path, ["screen_01"])

    assert at.exception == []
    assert len(call_log) == 4  # Plan A + Plan B, her biri 2 aşamalı (gözlem + grounded), tek ekran için
    assert all(c["image_bytes_sent"] for c in call_log)  # AI Görsel Analiz Modu'nda görsel GÖNDERİLMELİ

    results = at.session_state["a1_vision_results"]
    assert "screen_01" in results
    assert results["screen_01"]["a"]["outcome"].grounded is not None
    assert results["screen_01"]["b"]["outcome"].grounded is not None


def test_multi_screen_vision_workflow_and_storyboard_transfer(monkeypatch, tmp_path):
    at, call_log, _ = _run_vision_generation(monkeypatch, tmp_path, ["screen_01", "screen_02"])

    assert at.exception == []
    assert len(call_log) == 8  # 2 ekran x 2 model x 2 aşama
    results = at.session_state["a1_vision_results"]
    assert set(results.keys()) == {"screen_01", "screen_02"}

    # Tüm sahnelerde Plan A'yı kullan
    apply_all_btn = next(b for b in at.get("button") if b.key == "a1_vision_apply_all_a")
    apply_all_btn.click().run(timeout=15)

    selected = at.session_state["a1_vision_selected_scenes"]
    assert set(selected.keys()) == {"screen_01", "screen_02"}

    transfer_btn = next(b for b in at.get("button") if b.key == "a1_vision_transfer")
    assert transfer_btn.disabled is False
    transfer_btn.click().run(timeout=15)

    assert at.exception == []
    selected_storyboard = at.session_state["a1_selected_storyboard"]
    assert selected_storyboard is not None
    assert selected_storyboard["source_model_label"] == "AI Görsel Analiz"
    storyboard = selected_storyboard["storyboard"]
    assert len(storyboard["scenes"]) == 2
    assert [s["image_id"] for s in sorted(storyboard["scenes"], key=lambda s: s["scene_number"])] == [
        "screen_01",
        "screen_02",
    ]


def test_no_screenshot_bytes_written_to_csv(monkeypatch, tmp_path):
    _, _, csv_path = _run_vision_generation(monkeypatch, tmp_path, ["screen_01"])

    csv_content = csv_path.read_text(encoding="utf-8")
    # PNG dosya imzası/baytları veya base64 kodlu görsel içeriği CSV'de asla bulunmamalı.
    assert "PNG" not in csv_content
    assert "base64" not in csv_content.lower()
    # CSV yalnızca beklenen (küçük, sayısal/metin) alanları içermeli.
    assert "test-vision-model-a" in csv_content or "test-vision-model-b" in csv_content


def test_backward_compatibility_manual_note_project_still_works(monkeypatch, tmp_path):
    """Varsayılan (Güvenli Kurumsal Mod) davranış, mevcut manuel-not projeleriyle değişmeden çalışmalı."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    assert at.exception == []

    # Mod değiştirilmeden varsayılan olarak "safe" olmalı ve storyboard
    # üretim bölümü (metin tabanlı) görünmeli.
    assert at.session_state["a1_workflow_mode"] == "safe"
    _seed_project(at, ["screen_01"], note="Ana panelden gidilir.")
    at.run(timeout=15)

    buttons = [b.key for b in at.get("button")]
    assert "a1_storyboard_generate" in buttons
    assert "a1_vision_generate" not in buttons  # Güvenli modda görsel analiz bölümü hiç render edilmez
