import copy
import io

import pytest
from PIL import Image

from schemas.a1_vision_models import validate_grounded_scene_result, validate_vision_scene_result
from services.a1_knowledge_service import load_knowledge_base
from services.bedrock_client import ModelCallResult
from services.a1_vision_service import (
    build_highlight_preview,
    build_vision_storyboard,
    build_vision_user_prompt,
    compute_grounding_source_ids,
    detect_image_mime_type,
    grounded_result_to_storyboard_scene,
    run_grounded_vision_analysis,
    run_vision_analysis,
    vision_result_to_storyboard_scene,
)

VALID_VISION_JSON = {
    "image_id": "screen_01",
    "scene_title": "Yeni yolculuk başlatma",
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


def _png_bytes(w=200, h=100, color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_build_vision_user_prompt_contains_context_not_bytes():
    prompt = build_vision_user_prompt(
        "screen_01", 1, "Ana panel", "Not metni", "Genel amaç", "Trainer", "Kurumsal", "Sonraki: screen_02"
    )
    assert "screen_01" in prompt
    assert "Ana panel" in prompt
    assert "Genel amaç" in prompt
    assert "Trainer" in prompt
    # Görsel baytları asla metin prompt'una gömülmez
    assert "base64" not in prompt.lower()


def test_detect_image_mime_type_png():
    assert detect_image_mime_type(_png_bytes()) == "image/png"


def test_detect_image_mime_type_unreadable_defaults_to_png():
    assert detect_image_mime_type(b"not an image") == "image/png"


def test_run_vision_analysis_success(monkeypatch):
    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        assert image_bytes is not None  # görsel gerçekten çağrıya geçiyor
        return ModelCallResult(
            model_id=model_id,
            raw_text="{...}",
            parsed_json=copy.deepcopy(VALID_VISION_JSON),
            success=True,
            api_call_success=True,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=500.0,
        )

    monkeypatch.setattr("services.a1_vision_service.call_model", fake_call_model)

    outcome = run_vision_analysis(
        "test-vision-model",
        "system prompt",
        _png_bytes(),
        "screen_01",
        1,
        "Ana panel",
        None,
        "Genel amaç",
        "Trainer",
        "Kurumsal",
        0.2,
        1500,
    )

    assert outcome.call_result.success is True
    assert outcome.schema_valid is True
    assert outcome.validated is not None
    assert outcome.validated.image_id == "screen_01"
    assert outcome.business_result is not None
    assert outcome.business_result["passed"] is True


def test_run_vision_analysis_schema_invalid(monkeypatch):
    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        return ModelCallResult(
            model_id=model_id,
            raw_text="{...}",
            parsed_json={"image_id": "screen_01"},  # eksik zorunlu alanlar
            success=True,
            api_call_success=True,
        )

    monkeypatch.setattr("services.a1_vision_service.call_model", fake_call_model)

    outcome = run_vision_analysis(
        "test-vision-model", "system prompt", _png_bytes(), "screen_01", 1, None, None, None, "Trainer", "Kurumsal", 0.2, 1500
    )
    assert outcome.schema_valid is False
    assert outcome.validated is None
    assert outcome.schema_error is not None


def test_run_vision_analysis_mismatched_image_id_flagged_by_business_layer(monkeypatch):
    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        data = copy.deepcopy(VALID_VISION_JSON)
        data["image_id"] = "screen_99"
        return ModelCallResult(model_id=model_id, raw_text="{...}", parsed_json=data, success=True, api_call_success=True)

    monkeypatch.setattr("services.a1_vision_service.call_model", fake_call_model)

    outcome = run_vision_analysis(
        "test-vision-model", "system prompt", _png_bytes(), "screen_01", 1, None, None, None, "Trainer", "Kurumsal", 0.2, 1500
    )
    assert outcome.schema_valid is True
    assert outcome.business_result["passed"] is False
    assert any("eşleşmiyor" in e for e in outcome.business_result["errors"])


def test_vision_result_to_storyboard_scene_preserves_extended_fields():
    validated = validate_vision_scene_result(VALID_VISION_JSON)
    scene = vision_result_to_storyboard_scene(validated, scene_number=3)

    assert scene["scene_number"] == 3
    assert scene["image_id"] == "screen_01"
    assert scene["highlight_rect"] == VALID_VISION_JSON["highlight_rect"]
    assert scene["action_type"] == "click"
    assert scene["target_label"] == "Yeni Yolculuk Ekle butonu"
    assert scene["instruction_text"] == "Yeni Yolculuk Ekle butonuna tıklayın."
    assert scene["cursor_enabled"] is True
    assert scene["click_effect_enabled"] is True
    assert scene["requires_review"] is True
    assert 4 <= scene["duration_seconds"] <= 8  # storyboard şemasıyla uyumlu varsayılan süre


def test_vision_result_to_storyboard_scene_non_click_action_disables_click_effect():
    data = copy.deepcopy(VALID_VISION_JSON)
    data["action_type"] = "review"
    data["highlight_rect"] = None
    validated = validate_vision_scene_result(data)
    scene = vision_result_to_storyboard_scene(validated, scene_number=1)
    assert scene["cursor_enabled"] is False
    assert scene["click_effect_enabled"] is False
    assert scene["highlight_rect"] is None


def test_vision_selected_scene_is_independent_copy_not_mutating_original():
    validated = validate_vision_scene_result(VALID_VISION_JSON)
    scene = copy.deepcopy(vision_result_to_storyboard_scene(validated, scene_number=1))

    scene["scene_title"] = "Değiştirilmiş başlık"
    scene["highlight_rect"]["x"] = 0.0

    assert validated.scene_title == "Yeni yolculuk başlatma"
    assert validated.highlight_rect.x == 0.69


def test_build_vision_storyboard_computes_total_duration():
    validated = validate_vision_scene_result(VALID_VISION_JSON)
    scene1 = vision_result_to_storyboard_scene(validated, 1, duration_seconds=5)
    scene2 = vision_result_to_storyboard_scene(validated, 2, duration_seconds=6)
    storyboard = build_vision_storyboard("Test", "Trainer", "Kurumsal", [scene1, scene2])
    assert storyboard["total_duration_seconds"] == 11
    assert len(storyboard["scenes"]) == 2
    assert storyboard["closing_text"]


def test_build_highlight_preview_returns_original_when_no_rect():
    original = _png_bytes()
    preview = build_highlight_preview(original, None)
    assert preview == original


def test_build_highlight_preview_draws_when_rect_present():
    validated = validate_vision_scene_result(VALID_VISION_JSON)
    original = _png_bytes(400, 300)
    preview = build_highlight_preview(original, validated.highlight_rect)
    assert preview != original
    with Image.open(io.BytesIO(preview)) as img:
        assert img.size == (400, 300)


# --- Faz 4B: iki aşamalı, bilgi tabanına bağlı (grounded) akış ---------------

VALID_OBSERVATION_JSON = {
    "image_id": "screen_01",
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "detected_visible_labels": ["Yeni Yolculuk Ekle"],
    "possible_primary_target": "Yeni Yolculuk Ekle",
    "preliminary_action_type": "click",
    "preliminary_highlight_rect": {"x": 0.70, "y": 0.42, "width": 0.15, "height": 0.08},
    "confidence": 0.88,
    "visual_uncertainties": [],
}

VALID_GROUNDED_JSON = {
    "image_id": "screen_01",
    "matched_screen_id": "dashboard",
    "matched_screen_name": "Ana Sayfa",
    "screen_match_score": 0.9,
    "scene_title": "Yeni yolculuk başlatma",
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "primary_target": "Yeni Yolculuk Ekle",
    "target_element_id": "dashboard_new_journey_button",
    "action_type": "click",
    "instruction_text": "Yeni Yolculuk Ekle butonuna tıklayın.",
    "narration": "Ana paneldeki Yeni Yolculuk Ekle butonuna tıklayın.",
    "on_screen_text": "Yeni Yolculuk Ekle",
    "highlight_description": "Yolculuk kartındaki buton",
    "highlight_rect": {"x": 0.70, "y": 0.42, "width": 0.15, "height": 0.08},
    "confidence": 0.9,
    "requires_review": True,
    "grounding_source_ids": ["screen:dashboard", "element:dashboard_new_journey_button"],
    "grounding_warnings": [],
}


@pytest.fixture(scope="module")
def real_kb():
    return load_knowledge_base()


def _fake_two_stage_call_model(observation_json=None, grounded_json=None):
    """observation_json/grounded_json None ise varsayılan geçerli şablonlar kullanılır.
    build_grounded_user_prompt yalnızca "GROUNDING VERİSİ" başlığıyla üretildiği için
    bu işaretle iki aşama birbirinden ayırt edilir."""

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        is_grounded_stage = "GROUNDING VERİSİ" in user_prompt
        if is_grounded_stage:
            data = copy.deepcopy(grounded_json if grounded_json is not None else VALID_GROUNDED_JSON)
        else:
            data = copy.deepcopy(observation_json if observation_json is not None else VALID_OBSERVATION_JSON)
        return ModelCallResult(
            model_id=model_id,
            raw_text="{...}",
            parsed_json=data,
            success=True,
            api_call_success=True,
            input_tokens=100,
            output_tokens=80,
            total_tokens=180,
            latency_ms=400.0,
            estimated_cost_usd=0.0005,
        )

    return fake_call_model


def test_run_grounded_vision_analysis_confident_match_overrides_model_fields(monkeypatch, real_kb):
    # Model, farklı bir screen_id/target_element_id "iddia etse" bile bu alanlar
    # deterministik eşleştirme sonucuna göre üzerine yazılmalı (KB gerçekleri
    # modelin serbest metnine bırakılmaz).
    tampered_grounded = copy.deepcopy(VALID_GROUNDED_JSON)
    tampered_grounded["matched_screen_id"] = "journeys_list"
    tampered_grounded["target_element_id"] = "journeys_list_add_button"
    tampered_grounded["grounding_source_ids"] = ["screen:journeys_list"]

    monkeypatch.setattr(
        "services.a1_vision_service.call_model",
        _fake_two_stage_call_model(grounded_json=tampered_grounded),
    )

    outcome = run_grounded_vision_analysis(
        "test-vision-model",
        "observation system prompt",
        "grounded system prompt",
        _png_bytes(),
        "screen_01",
        1,
        "Ana panel",
        None,
        "Genel amaç",
        "Trainer",
        "Kurumsal",
        real_kb,
        0.2,
        1500,
    )

    assert outcome.observation is not None
    assert outcome.grounded is not None
    # Deterministik eşleştirme "Yeni Yolculuk Ekle" etiketinden dashboard'a işaret eder;
    # modelin "journeys_list" iddiası göz ardı edilmeli.
    assert outcome.grounded.matched_screen_id == "dashboard"
    assert outcome.grounded.matched_screen_name == "Ana Sayfa"
    assert outcome.grounded.target_element_id == "dashboard_new_journey_button"
    assert outcome.grounded.grounding_source_ids == ["screen:dashboard", "element:dashboard_new_journey_button"]
    assert outcome.grounded.requires_review is True
    assert outcome.business_result["passed"] is True


def test_run_grounded_vision_analysis_low_confidence_no_match(monkeypatch, real_kb):
    unmatched_observation = copy.deepcopy(VALID_OBSERVATION_JSON)
    unmatched_observation["detected_visible_labels"] = ["Tamamen alakasız bir etiket"]
    unmatched_observation["possible_primary_target"] = "Tamamen alakasız bir etiket"

    monkeypatch.setattr(
        "services.a1_vision_service.call_model",
        _fake_two_stage_call_model(observation_json=unmatched_observation),
    )

    outcome = run_grounded_vision_analysis(
        "test-vision-model",
        "observation system prompt",
        "grounded system prompt",
        _png_bytes(),
        "screen_01",
        1,
        None,
        None,
        None,
        "Trainer",
        "Kurumsal",
        real_kb,
        0.2,
        1500,
    )

    assert outcome.screen_match["matched_screen_id"] is None
    assert outcome.grounded.matched_screen_id is None
    assert outcome.grounded.target_element_id is None
    # "Ekran bilgi tabanıyla güvenilir biçimde eşleştirilemedi." uyarısı tek
    # kaynaktan (validate_grounded_result) gelmeli, tekrarlanmamalı.
    no_match_warnings = [
        w for w in outcome.grounded.grounding_warnings if "güvenilir biçimde eşleştirilemedi" in w
    ]
    assert len(no_match_warnings) == 1


def test_run_grounded_vision_analysis_workflow_order_aware_matching(monkeypatch, real_kb):
    # "Geri" tek başına belirsiz olabilir; beklenen adım sırası (4. adım =
    # journey_create_activities) eşleştirmeyi netleştirmeli.
    observation = copy.deepcopy(VALID_OBSERVATION_JSON)
    observation["detected_visible_labels"] = ["Geri"]
    observation["possible_primary_target"] = "Geri"
    grounded = copy.deepcopy(VALID_GROUNDED_JSON)
    grounded["primary_target"] = "Geri"

    monkeypatch.setattr(
        "services.a1_vision_service.call_model",
        _fake_two_stage_call_model(observation_json=observation, grounded_json=grounded),
    )

    outcome = run_grounded_vision_analysis(
        "test-vision-model",
        "observation system prompt",
        "grounded system prompt",
        _png_bytes(),
        "screen_04",
        4,
        None,
        None,
        None,
        "Trainer",
        "Kurumsal",
        real_kb,
        0.2,
        1500,
        workflow_id="create_journey",
        expected_order=4,
    )

    assert outcome.screen_match["matched_screen_id"] == "journey_create_activities"
    assert outcome.grounded.matched_screen_id == "journey_create_activities"
    assert "workflow:create_journey:step:4" in outcome.grounded.grounding_source_ids


def test_run_grounded_vision_analysis_observation_schema_invalid_skips_stage_two(monkeypatch, real_kb):
    monkeypatch.setattr(
        "services.a1_vision_service.call_model",
        _fake_two_stage_call_model(observation_json={"image_id": "screen_01"}),  # eksik zorunlu alanlar
    )

    outcome = run_grounded_vision_analysis(
        "test-vision-model",
        "observation system prompt",
        "grounded system prompt",
        _png_bytes(),
        "screen_01",
        1,
        None,
        None,
        None,
        "Trainer",
        "Kurumsal",
        real_kb,
        0.2,
        1500,
    )

    assert outcome.observation_schema_valid is False
    assert outcome.observation is None
    assert outcome.grounded_call_result is None
    assert outcome.grounded is None
    assert outcome.business_result is None


def test_compute_grounding_source_ids_includes_screen_element_and_workflow_step():
    screen_match = {"matched_screen_id": "dashboard"}
    target_match = {"target_element_id": "dashboard_new_journey_button"}
    source_ids = compute_grounding_source_ids(screen_match, target_match, "create_journey", 1)
    assert source_ids == ["screen:dashboard", "element:dashboard_new_journey_button", "workflow:create_journey:step:1"]


def test_compute_grounding_source_ids_empty_when_no_match():
    source_ids = compute_grounding_source_ids(None, None, None, None)
    assert source_ids == []


def test_grounded_result_to_storyboard_scene_preserves_grounding_metadata():
    grounded = validate_grounded_scene_result(VALID_GROUNDED_JSON)
    scene = grounded_result_to_storyboard_scene(grounded, scene_number=2)

    assert scene["scene_number"] == 2
    assert scene["image_id"] == "screen_01"
    assert scene["matched_screen_id"] == "dashboard"
    assert scene["target_element_id"] == "dashboard_new_journey_button"
    assert scene["grounding_source_ids"] == ["screen:dashboard", "element:dashboard_new_journey_button"]
    assert scene["grounding_warnings"] == []
    assert scene["requires_review"] is True
    assert scene["cursor_enabled"] is True
    assert scene["click_effect_enabled"] is True


def test_grounded_result_to_storyboard_scene_is_independent_copy():
    grounded = validate_grounded_scene_result(VALID_GROUNDED_JSON)
    scene = copy.deepcopy(grounded_result_to_storyboard_scene(grounded, scene_number=1))

    scene["grounding_source_ids"].append("screen:tampered")
    scene["scene_title"] = "Değiştirilmiş"

    assert grounded.grounding_source_ids == ["screen:dashboard", "element:dashboard_new_journey_button"]
    assert grounded.scene_title == "Yeni yolculuk başlatma"
