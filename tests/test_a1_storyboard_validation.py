from schemas.a1_project_models import validate_tutorial_project
from services.a1_storyboard_validation import validate_storyboard_business_rules

PROJECT_DATA = {
    "title": "Yeni Öğrenme Yolculuğu Oluşturma",
    "target_audience": "Trainer",
    "tone": "Kurumsal",
    "working_mode": "safe",
    "screens": [
        {
            "image_id": "screen_01",
            "original_file_name": "screen_01_dashboard.png",
            "scene_label": "Ana panel",
            "note": "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.",
            "order": 1,
            "width": 1920,
            "height": 1080,
        },
        {
            "image_id": "screen_02",
            "original_file_name": "screen_02_journeys.png",
            "scene_label": "Öğrenme yolculukları",
            "note": "Yeni Yolculuk Oluştur butonuna tıklanır.",
            "order": 2,
            "width": 1920,
            "height": 1080,
        },
    ],
}


def _project(**overrides):
    data = dict(PROJECT_DATA)
    data.update(overrides)
    return validate_tutorial_project(data)


def _scene(scene_number, image_id, note_based_narration, requires_review=False, extra_text="", scene_id=None):
    return {
        "scene_id": scene_id or f"{image_id}_step_{scene_number:02d}",
        "scene_number": scene_number,
        "image_id": image_id,
        "scene_title": f"Sahne {scene_number}",
        "duration_seconds": 6,
        "narration": note_based_narration + extra_text,
        "on_screen_text": "Kısa metin",
        "transition": "fade",
        "zoom_enabled": True,
        "highlight_description": "Vurgu" + extra_text,
        "requires_review": requires_review,
    }


def _storyboard(scenes, **overrides):
    data = {
        "title": "Yeni Öğrenme Yolculuğu Oluşturma",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": scenes,
        "total_duration_seconds": sum(s["duration_seconds"] for s in scenes),
        "closing_text": "Kapanış.",
    }
    data.update(overrides)
    return data


def test_valid_storyboard_passes_business_rules():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is True
    assert result["errors"] == []
    assert result["scenes_validated"] == 2


def test_unknown_image_id_fails():
    project = _project()
    scenes = [
        _scene(1, "screen_99", "Bilinmeyen ekran."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("Bilinmeyen image_id" in e for e in result["errors"])


def test_missing_source_image_id_fails():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("Kullanılmayan kaynak ekran" in e for e in result["errors"])


def test_excluded_image_id_does_not_trigger_missing_error():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe", excluded_image_ids={"screen_02"})
    assert result["passed"] is True
    assert not any("Kullanılmayan kaynak ekran" in e for e in result["errors"])


def test_repeated_image_id_allowed_when_all_source_screens_used():
    # Faz 4C: screen_01 iki alt sahneye bölünmüş, screen_02 tek sahne — hepsi
    # kullanıldığı için (repeated image_id dahil) hata OLUŞMAMALI.
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_01", "Aynı ekranın ikinci alt sahnesi."),
        _scene(3, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is True
    assert result["errors"] == []


def test_repeated_image_id_still_requires_all_screens_used():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_01", "Aynı ekran tekrar kullanıldı."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("Kullanılmayan kaynak ekran" in e for e in result["errors"])
    assert not any("Birden fazla kez kullanılan" in e for e in result["errors"])


def test_missing_scene_id_fails_business_rules():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    del scenes[0]["scene_id"]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("scene_id" in e for e in result["errors"])


def test_duplicate_scene_id_fails_business_rules():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.", scene_id="dup"),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır.", scene_id="dup"),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("scene_id değerleri benzersiz" in e for e in result["errors"])


def test_wrong_source_order_fails():
    project = _project()
    scenes = [
        _scene(1, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
        _scene(2, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("sırası korunmamış" in e for e in result["errors"])


def test_extra_scenes_for_repeated_image_allowed():
    # Faz 4C: kaynak ekran sayısından FAZLA sahne olması (screen_02'nin iki
    # alt sahneye bölünmesi) artık bir hata değildir.
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
        _scene(3, "screen_02", "Ekstra alt sahne."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is True
    assert result["errors"] == []


def test_incorrect_total_duration_fails():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes, total_duration_seconds=999)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("Toplam süre tutarsız" in e for e in result["errors"])


def test_unsupported_completion_claim_produces_warning_not_error():
    project = _project()
    scenes = [
        _scene(
            1,
            "screen_01",
            "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.",
            extra_text=" Yolculuk başarıyla oluşturuldu.",
        ),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is True
    assert any("başarıyla oluşturuldu" in w for w in result["warnings"])


def test_safe_mode_requires_review_true_fails():
    project = _project(working_mode="safe")
    scenes = [
        _scene(
            1,
            "screen_01",
            "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.",
            requires_review=True,
        ),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("Güvenli modda requires_review" in e for e in result["errors"])


def test_assisted_mode_without_requires_review_warns():
    project = _project(working_mode="assisted")
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "assisted")
    assert result["passed"] is True
    assert any("hiçbir sahne requires_review" in w for w in result["warnings"])


def test_assisted_mode_with_requires_review_no_warning():
    project = _project(working_mode="assisted")
    scenes = [
        _scene(
            1,
            "screen_01",
            "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir.",
            requires_review=True,
        ),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "assisted")
    assert result["passed"] is True
    assert not any("hiçbir sahne requires_review" in w for w in result["warnings"])


def test_on_screen_text_length_checked_in_business_rules():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    scenes[0]["on_screen_text"] = "x" * 40
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is True


def test_on_screen_text_over_limit_fails_business_rules():
    project = _project()
    scenes = [
        _scene(1, "screen_01", "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."),
        _scene(2, "screen_02", "Yeni Yolculuk Oluştur butonuna tıklanır."),
    ]
    scenes[0]["on_screen_text"] = "x" * 41
    storyboard = _storyboard(scenes)
    result = validate_storyboard_business_rules(storyboard, project, "safe")
    assert result["passed"] is False
    assert any("on_screen_text" in e for e in result["errors"])
