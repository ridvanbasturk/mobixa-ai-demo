import io
import json

import pytest
from PIL import Image
from pydantic import ValidationError

from schemas.a1_project_models import validate_tutorial_project
from services.a1_project_service import (
    generate_image_id,
    move_screen_down,
    move_screen_up,
    read_image_dimensions,
    remove_screen,
    validate_image_extension,
)

VALID_SCREEN = {
    "image_id": "screen_01",
    "original_file_name": "screen_01_dashboard.png",
    "scene_label": "Ana panel",
    "note": "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.",
    "order": 1,
    "width": 1920,
    "height": 1080,
}


def _make_project(screens, **overrides):
    data = {
        "title": "Yeni Öğrenme Yolculuğu Oluşturma",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "working_mode": "safe",
        "screens": screens,
    }
    data.update(overrides)
    return data


def _png_bytes(width=100, height=50) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, format="PNG")
    return buf.getvalue()


# --- Pydantic schema tests -------------------------------------------------


def test_valid_project_passes():
    data = _make_project([dict(VALID_SCREEN)])
    project = validate_tutorial_project(data)
    assert project.title == "Yeni Öğrenme Yolculuğu Oluşturma"
    assert len(project.screens) == 1


def test_empty_title_fails():
    data = _make_project([dict(VALID_SCREEN)], title="   ")
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_no_screens_fails():
    data = _make_project([])
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_empty_scene_note_fails():
    screen = dict(VALID_SCREEN, note="   ")
    data = _make_project([screen])
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_duplicate_image_id_fails():
    screens = [
        dict(VALID_SCREEN, image_id="screen_01", order=1),
        dict(VALID_SCREEN, image_id="screen_01", order=2),
    ]
    data = _make_project(screens)
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_duplicate_order_fails():
    screens = [
        dict(VALID_SCREEN, image_id="screen_01", order=1),
        dict(VALID_SCREEN, image_id="screen_02", order=1),
    ]
    data = _make_project(screens)
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_non_consecutive_order_fails():
    screens = [
        dict(VALID_SCREEN, image_id="screen_01", order=1),
        dict(VALID_SCREEN, image_id="screen_02", order=3),
    ]
    data = _make_project(screens)
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_invalid_target_audience_fails():
    data = _make_project([dict(VALID_SCREEN)], target_audience="Manager")
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_invalid_tone_fails():
    data = _make_project([dict(VALID_SCREEN)], tone="Rahat")
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_invalid_working_mode_fails():
    data = _make_project([dict(VALID_SCREEN)], working_mode="turbo")
    with pytest.raises(ValidationError):
        validate_tutorial_project(data)


def test_json_export_has_no_binary_data():
    data = _make_project([dict(VALID_SCREEN)])
    project = validate_tutorial_project(data)
    exported = json.loads(json.dumps(project.model_dump(), ensure_ascii=False))
    assert "image_bytes" not in exported["screens"][0]
    assert "base64" not in json.dumps(exported)
    assert exported["screens"][0]["image_id"] == "screen_01"


# --- Image extension / dimension tests ------------------------------------


def test_unsupported_extension_rejected():
    error = validate_image_extension("diagram.gif")
    assert error is not None
    assert "Desteklenmeyen" in error


def test_supported_extension_accepted():
    assert validate_image_extension("screen.png") is None
    assert validate_image_extension("screen.JPG") is None


def test_valid_png_dimensions_read():
    dims, error = read_image_dimensions(_png_bytes(200, 100), "screen.png")
    assert error is None
    assert dims == (200, 100)


def test_corrupted_image_produces_turkish_error():
    dims, error = read_image_dimensions(b"not a real image", "screen.png")
    assert dims is None
    assert error is not None
    assert "bozuk" in error.lower() or "okunam" in error.lower()


def test_unsupported_extension_short_circuits_dimension_read():
    dims, error = read_image_dimensions(_png_bytes(), "screen.gif")
    assert dims is None
    assert "Desteklenmeyen" in error


# --- Stable image_id generation --------------------------------------------


def test_stable_image_id_generation():
    assert generate_image_id(1) == "screen_01"
    assert generate_image_id(2) == "screen_02"
    assert generate_image_id(10) == "screen_10"


# --- Reordering / removal ---------------------------------------------------


def _screens(n):
    return [
        {
            "image_id": generate_image_id(i + 1),
            "original_file_name": f"file_{i + 1}.png",
            "scene_label": None,
            "note": f"Not {i + 1}",
            "order": i + 1,
            "width": 100,
            "height": 100,
        }
        for i in range(n)
    ]


def test_move_scene_up():
    screens = _screens(3)
    move_screen_up(screens, 1)
    assert [s["image_id"] for s in screens] == ["screen_02", "screen_01", "screen_03"]
    assert [s["order"] for s in screens] == [1, 2, 3]


def test_move_scene_up_at_top_is_noop():
    screens = _screens(3)
    move_screen_up(screens, 0)
    assert [s["image_id"] for s in screens] == ["screen_01", "screen_02", "screen_03"]


def test_move_scene_down():
    screens = _screens(3)
    move_screen_down(screens, 0)
    assert [s["image_id"] for s in screens] == ["screen_02", "screen_01", "screen_03"]
    assert [s["order"] for s in screens] == [1, 2, 3]


def test_move_scene_down_at_bottom_is_noop():
    screens = _screens(3)
    move_screen_down(screens, 2)
    assert [s["image_id"] for s in screens] == ["screen_01", "screen_02", "screen_03"]


def test_remove_scene():
    screens = _screens(3)
    remove_screen(screens, 1)
    assert [s["image_id"] for s in screens] == ["screen_01", "screen_03"]
    assert [s["order"] for s in screens] == [1, 2]
