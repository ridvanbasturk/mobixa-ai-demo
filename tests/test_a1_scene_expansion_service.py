import copy

from schemas.a1_vision_models import validate_grounded_scene_result
from services.a1_duration_service import DURATION_SOURCE
from services.a1_knowledge_service import build_grounding_context, load_knowledge_base
from services.a1_scene_expansion_service import (
    build_expansion_user_prompt,
    expand_grounded_scene_to_storyboard_scenes,
    run_scene_expansion,
)
from services.bedrock_client import ModelCallResult

VALID_GROUNDED_JSON = {
    "image_id": "screen_03",
    "matched_screen_id": "journey_create_basic",
    "matched_screen_name": "Temel Bilgiler",
    "screen_match_score": 0.9,
    "scene_title": "Temel Bilgileri Tamamlama",
    "visible_ui_elements": ["Yolculuk Adı", "Başlangıç Tarihi", "Bitiş Tarihi", "İleri"],
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


def _grounded():
    return validate_grounded_scene_result(dict(VALID_GROUNDED_JSON))


def test_build_expansion_user_prompt_contains_approved_elements_not_bytes():
    kb = load_knowledge_base()
    grounded = _grounded()
    context = build_grounding_context(kb, "journey_create_basic", workflow_id="create_journey", step_order=3)
    prompt = build_expansion_user_prompt(
        grounded, kb, context, "create_journey", 3, "Test Videosu", "Trainer", "Kurumsal", None
    )
    assert "journey_create_basic" in prompt
    assert "basic_name_field" in prompt or "basic_next_button" in prompt
    assert "base64" not in prompt.lower()


def test_run_scene_expansion_success_produces_multiple_sub_scenes(monkeypatch):
    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        assert image_bytes is None  # alt sahne genişletmesi görsel GÖNDERMEZ
        return ModelCallResult(
            model_id=model_id,
            raw_text="{...}",
            parsed_json=copy.deepcopy(VALID_EXPANSION_JSON),
            success=True,
            api_call_success=True,
            input_tokens=100,
            output_tokens=80,
            total_tokens=180,
            latency_ms=300.0,
        )

    monkeypatch.setattr("services.a1_scene_expansion_service.call_model", fake_call_model)

    kb = load_knowledge_base()
    grounded = _grounded()
    context = build_grounding_context(kb, "journey_create_basic", workflow_id="create_journey", step_order=3)

    outcome = run_scene_expansion(
        "test-model", "system prompt", grounded, kb, context, "create_journey", 3,
        "Test Videosu", "Trainer", "Kurumsal", None, 0.2, 2000,
    )

    assert outcome.schema_valid is True
    assert outcome.parsed is not None
    assert len(outcome.parsed.sub_scenes) == 2
    assert all(s.requires_review for s in outcome.parsed.sub_scenes)
    assert outcome.business_result["passed"] is True


def test_run_scene_expansion_schema_invalid(monkeypatch):
    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        return ModelCallResult(
            model_id=model_id, raw_text="{...}", parsed_json={"image_id": "screen_03"},
            success=True, api_call_success=True,
        )

    monkeypatch.setattr("services.a1_scene_expansion_service.call_model", fake_call_model)

    kb = load_knowledge_base()
    grounded = _grounded()
    outcome = run_scene_expansion(
        "test-model", "system prompt", grounded, kb, None, None, None,
        "Test Videosu", "Trainer", "Kurumsal", None, 0.2, 2000,
    )
    assert outcome.schema_valid is False
    assert outcome.parsed is None
    assert outcome.business_result is None


def test_run_scene_expansion_forces_requires_review_true(monkeypatch):
    tampered = copy.deepcopy(VALID_EXPANSION_JSON)
    tampered["sub_scenes"][0]["requires_review"] = False

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens, image_bytes=None, image_mime_type="image/png"):
        return ModelCallResult(
            model_id=model_id, raw_text="{...}", parsed_json=tampered, success=True, api_call_success=True,
        )

    monkeypatch.setattr("services.a1_scene_expansion_service.call_model", fake_call_model)

    kb = load_knowledge_base()
    grounded = _grounded()
    outcome = run_scene_expansion(
        "test-model", "system prompt", grounded, kb, None, None, None,
        "Test Videosu", "Trainer", "Kurumsal", None, 0.2, 2000,
    )
    assert all(s.requires_review for s in outcome.parsed.sub_scenes)


def test_expand_grounded_scene_to_storyboard_scenes_produces_unique_scene_ids():
    from schemas.a1_scene_expansion_models import SubScene

    sub_scenes = [SubScene.model_validate(sd) for sd in VALID_EXPANSION_JSON["sub_scenes"]]
    scenes = expand_grounded_scene_to_storyboard_scenes("screen_03", sub_scenes, "journey_create_basic", 3)

    assert len(scenes) == 2
    assert scenes[0]["scene_id"] == "screen_03_step_01"
    assert scenes[1]["scene_id"] == "screen_03_step_02"
    assert scenes[0]["image_id"] == scenes[1]["image_id"] == "screen_03"
    assert scenes[0]["duration_source"] == DURATION_SOURCE
    assert scenes[0]["recommended_duration_seconds"] == scenes[0]["duration_seconds"]
    assert scenes[1]["highlight_rect"] == {"x": 0.8, "y": 0.85, "width": 0.1, "height": 0.06}
    assert scenes[0]["requires_review"] is True
    assert scenes[1]["target_element_id"] == "basic_next_button"


def test_expand_grounded_scene_to_storyboard_scenes_is_independent_copy():
    from schemas.a1_scene_expansion_models import SubScene

    sub_scenes = [SubScene.model_validate(sd) for sd in VALID_EXPANSION_JSON["sub_scenes"]]
    scenes = expand_grounded_scene_to_storyboard_scenes("screen_03", sub_scenes, "journey_create_basic", 1)
    scenes[0]["scene_title"] = "Değiştirilmiş"
    assert sub_scenes[0].scene_title == "Yolculuk adını girme"
