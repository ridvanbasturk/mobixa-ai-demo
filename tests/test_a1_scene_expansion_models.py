import pytest
from pydantic import ValidationError

from schemas.a1_scene_expansion_models import MAX_SUB_SCENES_PER_IMAGE, validate_scene_expansion_result

VALID_SUB_SCENE = {
    "sub_scene_key": "journey_name",
    "scene_title": "Yolculuk adını girme",
    "target_element_id": "journey_name_input",
    "action_type": "enter_text",
    "instruction_text": "Yolculuk Adı alanına açıklayıcı bir ad girin.",
    "narration": "Yolculuğu daha sonra kolayca tanıyabilmek için Yolculuk Adı alanına açıklayıcı bir ad girin.",
    "on_screen_text": "Yolculuk Adı",
    "highlight_description": "Yolculuk Adı giriş alanı",
    "highlight_rect": None,
    "cursor_enabled": True,
    "click_effect_enabled": False,
    "requires_review": True,
    "grounding_source_ids": ["screen:journey_create_basic", "element:journey_name_input"],
}


def _make_data(sub_scenes=None, **overrides):
    data = {
        "image_id": "screen_03",
        "sub_scenes": sub_scenes if sub_scenes is not None else [dict(VALID_SUB_SCENE)],
    }
    data.update(overrides)
    return data


def test_valid_single_sub_scene_passes():
    result = validate_scene_expansion_result(_make_data())
    assert result.image_id == "screen_03"
    assert len(result.sub_scenes) == 1


def test_valid_multiple_sub_scenes_passes():
    sub2 = dict(VALID_SUB_SCENE, sub_scene_key="dates", scene_title="Tarihleri ayarlama")
    result = validate_scene_expansion_result(_make_data(sub_scenes=[dict(VALID_SUB_SCENE), sub2]))
    assert len(result.sub_scenes) == 2


def test_empty_sub_scenes_fails():
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=[]))


def test_more_than_max_sub_scenes_fails():
    sub_scenes = [
        dict(VALID_SUB_SCENE, sub_scene_key=f"key_{i}") for i in range(MAX_SUB_SCENES_PER_IMAGE + 1)
    ]
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=sub_scenes))


def test_exactly_max_sub_scenes_passes():
    sub_scenes = [dict(VALID_SUB_SCENE, sub_scene_key=f"key_{i}") for i in range(MAX_SUB_SCENES_PER_IMAGE)]
    result = validate_scene_expansion_result(_make_data(sub_scenes=sub_scenes))
    assert len(result.sub_scenes) == MAX_SUB_SCENES_PER_IMAGE


def test_duplicate_sub_scene_key_fails():
    sub_scenes = [dict(VALID_SUB_SCENE), dict(VALID_SUB_SCENE)]
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=sub_scenes))


def test_blank_image_id_fails():
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(image_id="  "))


def test_target_element_id_optional_null_allowed():
    sub_scene = dict(VALID_SUB_SCENE, target_element_id=None, action_type="review")
    result = validate_scene_expansion_result(_make_data(sub_scenes=[sub_scene]))
    assert result.sub_scenes[0].target_element_id is None


def test_invalid_action_type_fails():
    sub_scene = dict(VALID_SUB_SCENE, action_type="delete")
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=[sub_scene]))


def test_on_screen_text_too_long_fails():
    sub_scene = dict(VALID_SUB_SCENE, on_screen_text="x" * 41)
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=[sub_scene]))


def test_blank_narration_fails():
    sub_scene = dict(VALID_SUB_SCENE, narration="   ")
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=[sub_scene]))


def test_blank_instruction_text_fails():
    sub_scene = dict(VALID_SUB_SCENE, instruction_text="")
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=[sub_scene]))


def test_grounding_source_ids_must_be_list():
    sub_scene = dict(VALID_SUB_SCENE, grounding_source_ids="not a list")
    with pytest.raises(ValidationError):
        validate_scene_expansion_result(_make_data(sub_scenes=[sub_scene]))
