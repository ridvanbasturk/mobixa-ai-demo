import pytest
from pydantic import ValidationError

from schemas.a1_storyboard_models import validate_storyboard

VALID_SCENE = {
    "scene_id": "screen_01_step_01",
    "scene_number": 1,
    "image_id": "screen_01",
    "scene_title": "Ana Panele Genel Bakış",
    "duration_seconds": 6,
    "narration": "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.",
    "on_screen_text": "Öğrenme Yolculukları",
    "transition": "fade",
    "zoom_enabled": True,
    "highlight_description": "Sol menüdeki bağlantı vurgulanır.",
    "requires_review": False,
}


def _make_storyboard(scenes, **overrides):
    data = {
        "title": "Yeni Öğrenme Yolculuğu Oluşturma",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": scenes,
        "total_duration_seconds": sum(s["duration_seconds"] for s in scenes),
        "closing_text": "Bu adımlarla yeni bir öğrenme yolculuğu oluşturabilirsiniz.",
    }
    data.update(overrides)
    return data


def test_valid_storyboard_passes():
    data = _make_storyboard([dict(VALID_SCENE)])
    storyboard = validate_storyboard(data)
    assert storyboard.title == "Yeni Öğrenme Yolculuğu Oluşturma"
    assert len(storyboard.scenes) == 1


def test_repeated_image_id_allowed():
    # Faz 4C: aynı ekran görüntüsü (alt sahne genişletmesiyle) birden fazla
    # sahnede kullanılabilir; artık image_id benzersizliği ARANMAZ.
    scenes = [
        dict(VALID_SCENE, scene_id="screen_01_step_01", scene_number=1, image_id="screen_01"),
        dict(VALID_SCENE, scene_id="screen_01_step_02", scene_number=2, image_id="screen_01"),
    ]
    data = _make_storyboard(scenes)
    storyboard = validate_storyboard(data)
    assert len(storyboard.scenes) == 2
    assert storyboard.scenes[0].image_id == storyboard.scenes[1].image_id == "screen_01"


def test_missing_scene_id_fails():
    scene = dict(VALID_SCENE)
    del scene["scene_id"]
    data = _make_storyboard([scene])
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_blank_scene_id_fails():
    scenes = [dict(VALID_SCENE, scene_id="   ")]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_duplicate_scene_id_fails():
    scenes = [
        dict(VALID_SCENE, scene_id="dup_id", scene_number=1, image_id="screen_01"),
        dict(VALID_SCENE, scene_id="dup_id", scene_number=2, image_id="screen_02"),
    ]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_duplicate_scene_number_fails():
    scenes = [
        dict(VALID_SCENE, scene_number=1, image_id="screen_01"),
        dict(VALID_SCENE, scene_number=1, image_id="screen_02"),
    ]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_non_consecutive_scene_number_fails():
    scenes = [
        dict(VALID_SCENE, scene_number=1, image_id="screen_01"),
        dict(VALID_SCENE, scene_number=3, image_id="screen_02"),
    ]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_duration_below_limit_fails():
    scenes = [dict(VALID_SCENE, duration_seconds=3)]
    data = _make_storyboard(scenes, total_duration_seconds=3)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_duration_above_limit_fails():
    # Faz 4C: üst sınır 14 sn'ye çıkarıldı (alt sahne genişletmesi için).
    scenes = [dict(VALID_SCENE, duration_seconds=15)]
    data = _make_storyboard(scenes, total_duration_seconds=15)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_duration_within_expanded_range_passes():
    scenes = [dict(VALID_SCENE, duration_seconds=12.5)]
    data = _make_storyboard(scenes, total_duration_seconds=12.5)
    storyboard = validate_storyboard(data)
    assert storyboard.scenes[0].duration_seconds == 12.5


def test_on_screen_text_too_long_fails():
    scenes = [dict(VALID_SCENE, on_screen_text="Bu metin kesinlikle kırk karakterden çok daha uzun bir metin")]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_invalid_transition_fails():
    scenes = [dict(VALID_SCENE, transition="wipe")]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_empty_narration_fails():
    scenes = [dict(VALID_SCENE, narration="   ")]
    data = _make_storyboard(scenes)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_empty_scenes_fails():
    data = _make_storyboard([])
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_non_positive_total_duration_fails():
    scenes = [dict(VALID_SCENE)]
    data = _make_storyboard(scenes, total_duration_seconds=0)
    with pytest.raises(ValidationError):
        validate_storyboard(data)


def test_empty_closing_text_fails():
    scenes = [dict(VALID_SCENE)]
    data = _make_storyboard(scenes, closing_text="")
    with pytest.raises(ValidationError):
        validate_storyboard(data)
