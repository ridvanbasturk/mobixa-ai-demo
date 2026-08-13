import pytest
from pydantic import ValidationError

from schemas.a1_vision_models import (
    validate_grounded_scene_result,
    validate_visual_observation,
    validate_vision_scene_result,
)

VALID_DATA = {
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


def _make_data(**overrides):
    data = dict(VALID_DATA)
    data.update(overrides)
    return data


def test_valid_vision_output_passes():
    result = validate_vision_scene_result(_make_data())
    assert result.image_id == "screen_01"
    assert result.action_type == "click"
    assert result.highlight_rect is not None


def test_valid_vision_output_without_highlight_rect_passes():
    result = validate_vision_scene_result(_make_data(highlight_rect=None))
    assert result.highlight_rect is None


def test_invalid_confidence_above_one_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(confidence=1.5))


def test_invalid_confidence_negative_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(confidence=-0.1))


def test_invalid_action_type_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(action_type="delete"))


def test_invalid_highlight_rect_out_of_bounds_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(
            _make_data(highlight_rect={"x": 0.9, "y": 0.5, "width": 0.3, "height": 0.2})
        )


def test_invalid_highlight_rect_negative_size_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(
            _make_data(highlight_rect={"x": 0.1, "y": 0.1, "width": -0.1, "height": 0.2})
        )


def test_blank_image_id_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(image_id="  "))


def test_blank_scene_title_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(scene_title=""))


def test_visible_ui_elements_must_be_list():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(visible_ui_elements="not a list"))


def test_on_screen_text_too_long_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(on_screen_text="x" * 41))


def test_on_screen_text_blank_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(on_screen_text=""))


def test_blank_primary_target_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(primary_target=""))


def test_blank_instruction_text_fails():
    with pytest.raises(ValidationError):
        validate_vision_scene_result(_make_data(instruction_text=""))


# --- Faz 4B: VisualObservation (Aşama 1) --------------------------------------

VALID_OBSERVATION_DATA = {
    "image_id": "screen_01",
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "detected_visible_labels": ["Yeni Yolculuk Ekle"],
    "possible_primary_target": "Yeni Yolculuk Ekle",
    "preliminary_action_type": "click",
    "preliminary_highlight_rect": {"x": 0.69, "y": 0.46, "width": 0.16, "height": 0.08},
    "confidence": 0.85,
    "visual_uncertainties": [],
}


def _make_observation_data(**overrides):
    data = dict(VALID_OBSERVATION_DATA)
    data.update(overrides)
    return data


def test_valid_visual_observation_passes():
    result = validate_visual_observation(_make_observation_data())
    assert result.image_id == "screen_01"
    assert result.preliminary_action_type == "click"


def test_visual_observation_allows_unknown_action_type():
    result = validate_visual_observation(_make_observation_data(preliminary_action_type="unknown"))
    assert result.preliminary_action_type == "unknown"


def test_visual_observation_allows_null_highlight_rect_when_unsure():
    result = validate_visual_observation(_make_observation_data(preliminary_highlight_rect=None))
    assert result.preliminary_highlight_rect is None


def test_visual_observation_invalid_action_type_fails():
    with pytest.raises(ValidationError):
        validate_visual_observation(_make_observation_data(preliminary_action_type="delete"))


def test_visual_observation_blank_possible_primary_target_fails():
    with pytest.raises(ValidationError):
        validate_visual_observation(_make_observation_data(possible_primary_target=""))


def test_visual_observation_detected_labels_must_be_list():
    with pytest.raises(ValidationError):
        validate_visual_observation(_make_observation_data(detected_visible_labels="not a list"))


def test_visual_observation_confidence_out_of_range_fails():
    with pytest.raises(ValidationError):
        validate_visual_observation(_make_observation_data(confidence=1.2))


def test_visual_observation_does_not_require_product_behavior_fields():
    """Aşama 1 çıktısında ürün davranışı/talimat/anlatım alanları YOKTUR — yalnızca gözlem."""
    result = validate_visual_observation(_make_observation_data())
    assert not hasattr(result, "instruction_text")
    assert not hasattr(result, "narration")


# --- Faz 4B: GroundedSceneResult (Aşama 2) ------------------------------------

VALID_GROUNDED_DATA = {
    "image_id": "screen_01",
    "matched_screen_id": "dashboard",
    "matched_screen_name": "Ana Sayfa",
    "screen_match_score": 0.91,
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
    "confidence": 0.90,
    "requires_review": True,
    "grounding_source_ids": ["screen:dashboard", "element:dashboard_new_journey_button"],
    "grounding_warnings": [],
}


def _make_grounded_data(**overrides):
    data = dict(VALID_GROUNDED_DATA)
    data.update(overrides)
    return data


def test_valid_grounded_scene_result_passes():
    result = validate_grounded_scene_result(_make_grounded_data())
    assert result.matched_screen_id == "dashboard"
    assert result.target_element_id == "dashboard_new_journey_button"
    assert result.grounding_source_ids == ["screen:dashboard", "element:dashboard_new_journey_button"]


def test_grounded_scene_result_allows_null_match_fields_when_no_match():
    result = validate_grounded_scene_result(
        _make_grounded_data(matched_screen_id=None, matched_screen_name=None, target_element_id=None)
    )
    assert result.matched_screen_id is None
    assert result.target_element_id is None


def test_grounded_scene_result_screen_match_score_out_of_range_fails():
    with pytest.raises(ValidationError):
        validate_grounded_scene_result(_make_grounded_data(screen_match_score=1.5))


def test_grounded_scene_result_grounding_source_ids_must_be_list():
    with pytest.raises(ValidationError):
        validate_grounded_scene_result(_make_grounded_data(grounding_source_ids="not a list"))


def test_grounded_scene_result_invalid_action_type_fails():
    with pytest.raises(ValidationError):
        validate_grounded_scene_result(_make_grounded_data(action_type="delete"))


def test_grounded_scene_result_on_screen_text_too_long_fails():
    with pytest.raises(ValidationError):
        validate_grounded_scene_result(_make_grounded_data(on_screen_text="x" * 41))


def test_grounded_scene_result_fields_are_mutable_for_deterministic_override():
    """run_grounded_vision_analysis, ayrıştırma sonrası bu alanları deterministik
    olarak üzerine yazar; bu yüzden model nesnesi bu alanlarda mutasyona izin vermeli."""
    result = validate_grounded_scene_result(_make_grounded_data(matched_screen_id="wrong_guess"))
    result.matched_screen_id = "dashboard"
    result.grounding_warnings = ["Bir uyarı"]
    assert result.matched_screen_id == "dashboard"
    assert result.grounding_warnings == ["Bir uyarı"]
