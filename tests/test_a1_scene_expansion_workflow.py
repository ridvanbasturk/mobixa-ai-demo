"""Faz 4C uçtan uca (Streamlit AppTest) iş akışı testi: grounded görsel analiz
seçimi -> ekranı alt sahnelere genişletme -> tekrarlı image_id içeren
storyboard'a aktarım. Hiçbir gerçek Bedrock çağrısı yapmaz
(services.a1_vision_service.call_model / services.a1_scene_expansion_service.call_model
sahtelenir).
"""
from __future__ import annotations

import copy
import io

from PIL import Image
from streamlit.testing.v1 import AppTest

from services.bedrock_client import ModelCallResult
from services.evaluation_logger import log_evaluation as real_log_evaluation

# journey_create_basic ekranının onaylı görünür etiketleriyle BİREBİR eşleşen
# bir gözlem; bu sayede deterministik ekran eşleştirmesi güvenle
# (skor eşik değerinin üstünde) "journey_create_basic" ekranını seçer.
BASIC_SCREEN_LABELS = [
    "Temel Bilgiler", "Aktiviteler", "Katılımcılar", "Özet ve Yayınlama",
    "Yolculuk Adı", "Başlangıç Tarihi", "Bitiş Tarihi", "Bitiş tarihi yok",
    "Şu andan 5 dakika sonraya ayarla", "İleri", "Vazgeç",
]

VALID_OBSERVATION_JSON = {
    "visible_ui_elements": BASIC_SCREEN_LABELS,
    "detected_visible_labels": BASIC_SCREEN_LABELS,
    "possible_primary_target": "İleri",
    "preliminary_action_type": "click",
    "preliminary_highlight_rect": None,
    "confidence": 0.9,
    "visual_uncertainties": [],
}

VALID_GROUNDED_JSON = {
    "matched_screen_id": "journey_create_basic",
    "matched_screen_name": "Temel Bilgiler",
    "screen_match_score": 0.9,
    "scene_title": "Temel Bilgileri Tamamlama",
    "visible_ui_elements": BASIC_SCREEN_LABELS,
    "primary_target": "İleri",
    "target_element_id": "basic_next_button",
    "action_type": "click",
    "instruction_text": "İleri butonuna tıklayın.",
    "narration": "Temel bilgileri doldurduktan sonra İleri butonuna tıklayın.",
    "on_screen_text": "İleri",
    "highlight_description": "İleri butonu",
    "highlight_rect": None,
    "confidence": 0.9,
    "requires_review": True,
    "grounding_source_ids": ["screen:journey_create_basic", "element:basic_next_button"],
    "grounding_warnings": [],
}

VALID_EXPANSION_JSON = {
    "image_id": "screen_03",
    "sub_scenes": [
        {
            "sub_scene_key": "journey_name",
            "scene_title": "Yolculuk adını girme",
            "target_element_id": "basic_name_field",
            "action_type": "enter_text",
            "instruction_text": "Yolculuk Adı alanına açıklayıcı bir ad girin.",
            "narration": "Yolculuğu daha sonra kolayca tanıyabilmek için Yolculuk Adı alanına açıklayıcı bir ad girin.",
            "on_screen_text": "Yolculuk Adı",
            "highlight_description": "Yolculuk Adı giriş alanı",
            "highlight_rect": None,
            "cursor_enabled": True,
            "click_effect_enabled": False,
            "requires_review": True,
            "grounding_source_ids": ["screen:journey_create_basic", "element:basic_name_field"],
        },
        {
            "sub_scene_key": "continue",
            "scene_title": "İleri ile devam etme",
            "target_element_id": "basic_next_button",
            "action_type": "click",
            "instruction_text": "İleri butonuna tıklayarak devam edin.",
            "narration": "Gerekli bilgileri girdikten sonra İleri butonuna tıklayarak devam edin.",
            "on_screen_text": "İleri",
            "highlight_description": "İleri butonu",
            "highlight_rect": {"x": 0.8, "y": 0.85, "width": 0.1, "height": 0.06},
            "cursor_enabled": True,
            "click_effect_enabled": True,
            "requires_review": True,
            "grounding_source_ids": ["screen:journey_create_basic", "element:basic_next_button"],
        },
    ],
}


def _png_bytes(w=400, h=300, color=(10, 20, 30)) -> bytes:
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


def _seed_project(at: AppTest, image_id="screen_03") -> None:
    screens = [
        {
            "image_id": image_id,
            "original_file_name": f"{image_id}.png",
            "scene_label": "Temel Bilgiler",
            "note": "Temel bilgiler doldurulur.",
            "order": 1,
            "width": 400,
            "height": 300,
        }
    ]
    at.session_state["a1_screens"] = screens
    at.session_state["a1_screen_bytes"] = {image_id: _png_bytes()}
    at.session_state["a1_export"] = {
        "title": "Test Projesi",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "working_mode": "safe",
        "screens": screens,
    }


def _fake_vision_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
    is_grounded_stage = "GROUNDING VERİSİ" in user_prompt
    data = copy.deepcopy(VALID_GROUNDED_JSON if is_grounded_stage else VALID_OBSERVATION_JSON)
    data["image_id"] = "screen_03"
    return ModelCallResult(
        model_id=model_id, raw_text="{...}", parsed_json=data, success=True, api_call_success=True,
        input_tokens=200, output_tokens=150, total_tokens=350, latency_ms=500.0, estimated_cost_usd=0.001,
    )


def _fake_expansion_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
    assert image_bytes is None  # alt sahne genişletmesi ekran görüntüsü GÖNDERMEMELİ
    return ModelCallResult(
        model_id=model_id, raw_text="{...}", parsed_json=copy.deepcopy(VALID_EXPANSION_JSON),
        success=True, api_call_success=True, input_tokens=120, output_tokens=90, total_tokens=210, latency_ms=300.0,
    )


def test_expand_screen_and_transfer_produces_repeated_image_id_storyboard(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A1_VISION_MODEL_A", "test-vision-model-a")
    monkeypatch.setenv("A1_VISION_MODEL_B", "test-vision-model-b")
    monkeypatch.setenv("A1_MODEL_A", "test-text-model-a")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    monkeypatch.setattr("services.a1_vision_service.call_model", _fake_vision_call_model)
    monkeypatch.setattr("services.a1_scene_expansion_service.call_model", _fake_expansion_call_model)
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    _seed_project(at)

    mode_radio = next(r for r in at.get("radio") if r.key == "a1_workflow_mode_radio")
    mode_radio.set_value("AI Görsel Analiz Modu")
    at.run(timeout=15)

    privacy_checkbox = next(c for c in at.get("checkbox") if c.key == "a1_vision_privacy_confirmed")
    privacy_checkbox.check()
    at.run(timeout=15)

    gen_btn = next(b for b in at.get("button") if b.key == "a1_vision_generate")
    gen_btn.click().run(timeout=30)
    assert at.exception == []

    results = at.session_state["a1_vision_results"]
    assert "screen_03" in results
    assert results["screen_03"]["a"]["outcome"].grounded.matched_screen_id == "journey_create_basic"

    use_a_btn = next(b for b in at.get("button") if b.key.startswith("a1_vision_use_screen_03_test-vision-model-a"))
    use_a_btn.click().run(timeout=15)
    assert at.exception == []
    assert len(at.session_state["a1_vision_selected_scenes"]["screen_03"]) == 1

    # Genişletme modeli seçici: maliyet için varsayılan olarak Gemma 4 31B
    # (tek aktif model) seçili olmalı; Qwen3 235B seçilebilir bir alternatif
    # olarak listede bulunmalı.
    expansion_selectbox = next(
        sb for sb in at.get("selectbox") if sb.key == "a1_expand_model_choice_screen_03"
    )
    assert expansion_selectbox.options == ["google.gemma-4-31b", "qwen.qwen3-235b-a22b-2507"]
    assert expansion_selectbox.value == "google.gemma-4-31b"

    expand_btn = next(b for b in at.get("button") if b.key == "a1_expand_screen_03")
    expand_btn.click().run(timeout=15)
    assert at.exception == []

    proposal = at.session_state["a1_expansion_results"]["screen_03"]["outcome"]
    assert proposal.parsed is not None
    assert len(proposal.parsed.sub_scenes) == 2

    apply_all_btn = next(b for b in at.get("button") if b.key == "a1_expand_apply_all_screen_03")
    apply_all_btn.click().run(timeout=15)
    assert at.exception == []

    selected_scenes = at.session_state["a1_vision_selected_scenes"]["screen_03"]
    assert len(selected_scenes) == 2
    assert selected_scenes[0]["image_id"] == selected_scenes[1]["image_id"] == "screen_03"
    scene_ids = [s["scene_id"] for s in selected_scenes]
    assert len(scene_ids) == len(set(scene_ids))
    assert all(s["requires_review"] for s in selected_scenes)

    transfer_btn = next(b for b in at.get("button") if b.key == "a1_vision_transfer")
    assert transfer_btn.disabled is False
    transfer_btn.click().run(timeout=15)
    assert at.exception == []

    storyboard = at.session_state["a1_selected_storyboard"]["storyboard"]
    assert len(storyboard["scenes"]) == 2
    image_ids = [s["image_id"] for s in storyboard["scenes"]]
    assert image_ids == ["screen_03", "screen_03"]
    scene_ids = [s["scene_id"] for s in storyboard["scenes"]]
    assert len(scene_ids) == len(set(scene_ids))
    scene_numbers = sorted(s["scene_number"] for s in storyboard["scenes"])
    assert scene_numbers == [1, 2]

    # Storyboard editörü (scene_id bazlı) sorunsuz render edilmeli.
    assert at.exception == []
    scene_id_captions = [c for c in at.get("caption") if c.value.startswith("scene_id:")]
    assert len(scene_id_captions) == 2
    assert any("birden fazla sahnede kullanılıyor" in c.value for c in scene_id_captions)

    duplicate_buttons = [b for b in at.get("button") if b.key.startswith("a1_sel_duplicate_")]
    remove_buttons = [b for b in at.get("button") if b.key.startswith("a1_sel_remove_")]
    assert len(duplicate_buttons) == 2
    assert len(remove_buttons) == 2
