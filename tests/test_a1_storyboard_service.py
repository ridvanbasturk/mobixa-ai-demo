import copy

from schemas.a1_storyboard_models import validate_storyboard
from services.a1_storyboard_service import (
    build_narration_text,
    duplicate_scene,
    generate_unique_scene_id,
    migrate_scene_ids,
    move_scene_down,
    move_scene_up,
    recalculate_total_duration,
    remove_scene,
)

VALID_SCENE = {
    "scene_id": "screen_01_step_01",
    "scene_number": 1,
    "image_id": "screen_01",
    "scene_title": "Sahne",
    "duration_seconds": 6,
    "narration": "Anlatım metni.",
    "on_screen_text": "Kısa metin",
    "transition": "fade",
    "zoom_enabled": True,
    "highlight_description": "Vurgu",
    "requires_review": False,
}


def _scenes(n):
    return [
        dict(
            VALID_SCENE,
            scene_id=f"screen_{i + 1:02d}_step_01",
            scene_number=i + 1,
            image_id=f"screen_{i + 1:02d}",
            scene_title=f"Sahne {i + 1}",
        )
        for i in range(n)
    ]


def test_move_scene_up():
    scenes = _scenes(3)
    move_scene_up(scenes, 1)
    assert [s["image_id"] for s in scenes] == ["screen_02", "screen_01", "screen_03"]
    assert [s["scene_number"] for s in scenes] == [1, 2, 3]


def test_move_scene_up_at_top_is_noop():
    scenes = _scenes(3)
    move_scene_up(scenes, 0)
    assert [s["image_id"] for s in scenes] == ["screen_01", "screen_02", "screen_03"]


def test_move_scene_down():
    scenes = _scenes(3)
    move_scene_down(scenes, 0)
    assert [s["image_id"] for s in scenes] == ["screen_02", "screen_01", "screen_03"]
    assert [s["scene_number"] for s in scenes] == [1, 2, 3]


def test_move_scene_down_at_bottom_is_noop():
    scenes = _scenes(3)
    move_scene_down(scenes, 2)
    assert [s["image_id"] for s in scenes] == ["screen_01", "screen_02", "screen_03"]


def test_total_duration_recalculation():
    scenes = _scenes(3)
    scenes[0]["duration_seconds"] = 4
    scenes[1]["duration_seconds"] = 5
    scenes[2]["duration_seconds"] = 8
    assert recalculate_total_duration(scenes) == 17


def test_narration_txt_export_contains_expected_sections():
    scenes = [
        dict(VALID_SCENE, scene_number=1, image_id="screen_01", scene_title="Ana Panel", narration="Ana panele gidilir."),
        dict(VALID_SCENE, scene_number=2, image_id="screen_02", scene_title="Yolculuklar", narration="Yolculuk oluşturulur."),
    ]
    text = build_narration_text("Yeni Öğrenme Yolculuğu Oluşturma", scenes, "Kapanış metni.")

    assert "Video Başlığı: Yeni Öğrenme Yolculuğu Oluşturma" in text
    assert "Sahne 1: Ana Panel" in text
    assert "Ana panele gidilir." in text
    assert "Sahne 2: Yolculuklar" in text
    assert "Yolculuk oluşturulur." in text
    assert "Kapanış:" in text
    assert "Kapanış metni." in text
    # Sahneler doğru sırada olmalı
    assert text.index("Sahne 1") < text.index("Sahne 2")


def test_narration_txt_export_orders_by_scene_number_not_list_order():
    scenes = [
        dict(VALID_SCENE, scene_number=2, image_id="screen_02", scene_title="İkinci", narration="İkinci anlatım."),
        dict(VALID_SCENE, scene_number=1, image_id="screen_01", scene_title="Birinci", narration="Birinci anlatım."),
    ]
    text = build_narration_text("Başlık", scenes, "Kapanış.")
    assert text.index("Sahne 1") < text.index("Sahne 2")


def test_selected_storyboard_deep_copy_does_not_mutate_original():
    scenes = _scenes(2)
    data = {
        "title": "Başlık",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": scenes,
        "total_duration_seconds": sum(s["duration_seconds"] for s in scenes),
        "closing_text": "Kapanış.",
    }
    validated = validate_storyboard(data)
    original_dump = validated.model_dump()

    selected_copy = copy.deepcopy(original_dump)
    selected_copy["scenes"][0]["scene_title"] = "Değiştirilmiş Başlık"
    selected_copy["closing_text"] = "Değiştirilmiş kapanış."

    assert original_dump["scenes"][0]["scene_title"] == "Sahne 1"
    assert original_dump["closing_text"] == "Kapanış."
    assert validated.scenes[0].scene_title == "Sahne 1"


# --- Faz 4C: scene_id göçü ------------------------------------------------


def _scene_without_scene_id(scene_number, image_id):
    scene = dict(VALID_SCENE, scene_number=scene_number, image_id=image_id)
    del scene["scene_id"]
    return scene


def test_migrate_scene_ids_generates_stable_ids_for_old_storyboard():
    storyboard = {
        "title": "Eski Storyboard",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [
            _scene_without_scene_id(1, "screen_01"),
            _scene_without_scene_id(2, "screen_02"),
        ],
        "total_duration_seconds": 12,
        "closing_text": "Kapanış.",
    }
    migrated = migrate_scene_ids(storyboard)
    assert migrated["scenes"][0]["scene_id"] == "screen_01_step_01"
    assert migrated["scenes"][1]["scene_id"] == "screen_02_step_01"
    validate_storyboard(migrated)  # artık şema doğrulamasından geçmeli


def test_migrate_scene_ids_numbers_repeated_image_occurrences():
    storyboard = {
        "title": "Genişletilmiş Storyboard",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [
            _scene_without_scene_id(1, "screen_03"),
            _scene_without_scene_id(2, "screen_03"),
            _scene_without_scene_id(3, "screen_03"),
        ],
        "total_duration_seconds": 18,
        "closing_text": "Kapanış.",
    }
    migrated = migrate_scene_ids(storyboard)
    assert [s["scene_id"] for s in migrated["scenes"]] == [
        "screen_03_step_01",
        "screen_03_step_02",
        "screen_03_step_03",
    ]


def test_migrate_scene_ids_does_not_mutate_original():
    storyboard = {
        "title": "Eski Storyboard",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [_scene_without_scene_id(1, "screen_01")],
        "total_duration_seconds": 6,
        "closing_text": "Kapanış.",
    }
    migrate_scene_ids(storyboard)
    assert "scene_id" not in storyboard["scenes"][0]


def test_migrate_scene_ids_leaves_existing_scene_id_untouched():
    storyboard = {
        "title": "Karışık Storyboard",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [
            dict(VALID_SCENE, scene_id="custom_id", scene_number=1, image_id="screen_01"),
            _scene_without_scene_id(2, "screen_02"),
        ],
        "total_duration_seconds": 12,
        "closing_text": "Kapanış.",
    }
    migrated = migrate_scene_ids(storyboard)
    assert migrated["scenes"][0]["scene_id"] == "custom_id"
    assert migrated["scenes"][1]["scene_id"] == "screen_02_step_01"


def test_generate_unique_scene_id_avoids_collision():
    existing = ["screen_01_step_01", "screen_01_step_02"]
    new_id = generate_unique_scene_id("screen_01", existing)
    assert new_id == "screen_01_step_03"
    assert new_id not in existing


# --- Faz 4C: sahne çoğaltma / kaldırma -------------------------------------


def test_duplicate_scene_creates_new_unique_scene_id_and_marks_review():
    scenes = _scenes(2)
    duplicate_scene(scenes, 0)
    assert len(scenes) == 3
    assert [s["image_id"] for s in scenes] == ["screen_01", "screen_01", "screen_02"]
    scene_ids = [s["scene_id"] for s in scenes]
    assert len(scene_ids) == len(set(scene_ids))
    assert scenes[1]["requires_review"] is True
    assert [s["scene_number"] for s in scenes] == [1, 2, 3]


def test_duplicate_scene_copies_editable_fields_independently():
    scenes = _scenes(1)
    duplicate_scene(scenes, 0)
    scenes[1]["scene_title"] = "Değiştirilmiş kopya"
    assert scenes[0]["scene_title"] == "Sahne 1"


def test_remove_scene_renumbers_remaining_scenes():
    scenes = _scenes(3)
    remove_scene(scenes, 1)
    assert len(scenes) == 2
    assert [s["image_id"] for s in scenes] == ["screen_01", "screen_03"]
    assert [s["scene_number"] for s in scenes] == [1, 2]


def test_remove_scene_keeps_at_least_one_scene():
    scenes = _scenes(1)
    remove_scene(scenes, 0)
    assert len(scenes) == 1
