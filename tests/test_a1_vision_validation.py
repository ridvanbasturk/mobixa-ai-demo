import pytest

from schemas.a1_scene_expansion_models import validate_scene_expansion_result
from schemas.a1_vision_models import (
    validate_grounded_scene_result,
    validate_visual_observation,
    validate_vision_scene_result,
)
from services.a1_knowledge_service import load_knowledge_base
from services.a1_vision_validation import (
    validate_grounded_result,
    validate_scene_expansion,
    validate_vision_result,
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


def _result(**overrides):
    data = dict(VALID_DATA)
    data.update(overrides)
    return validate_vision_scene_result(data)


def test_valid_result_passes():
    result = _result()
    report = validate_vision_result(result, "screen_01")
    assert report["passed"] is True
    assert report["errors"] == []


def test_mismatched_image_id_fails():
    result = _result(image_id="screen_02")
    report = validate_vision_result(result, "screen_01")
    assert report["passed"] is False
    assert any("eşleşmiyor" in e for e in report["errors"])


def test_low_confidence_produces_warning():
    result = _result(confidence=0.4)
    report = validate_vision_result(result, "screen_01")
    assert report["passed"] is True
    assert any("Güven skoru düşük" in w for w in report["warnings"])


def test_confidence_at_threshold_no_warning():
    result = _result(confidence=0.65)
    report = validate_vision_result(result, "screen_01")
    assert not any("Güven skoru düşük" in w for w in report["warnings"])


def test_click_without_highlight_rect_produces_warning():
    result = _result(highlight_rect=None)
    report = validate_vision_result(result, "screen_01")
    assert report["passed"] is True
    assert any("vurgu" in w.lower() for w in report["warnings"])


def test_missing_target_warning_for_placeholder_value():
    result = _result(primary_target="bilinmiyor")
    report = validate_vision_result(result, "screen_01")
    assert any("belirsiz/placeholder" in w for w in report["warnings"])


def test_requires_review_false_produces_warning():
    result = _result(requires_review=False)
    report = validate_vision_result(result, "screen_01")
    assert any("requires_review=false" in w for w in report["warnings"])


def test_unsupported_completion_claim_produces_warning():
    result = _result(narration="Yolculuk başarıyla oluşturuldu ve kaydedildi.")
    report = validate_vision_result(result, "screen_01")
    assert any("başarıyla oluşturuldu" in w for w in report["warnings"])
    assert report["passed"] is True


def test_select_action_without_highlight_does_not_trigger_click_warning():
    # Yalnızca "click" eylemi vurgu (highlight) uyarısı üretir; "select" için
    # bu uyarı beklenmez.
    result = _result(action_type="select", highlight_rect=None)
    report = validate_vision_result(result, "screen_01")
    assert not any("'click' eylemi" in w for w in report["warnings"])


def test_information_action_without_highlight_no_click_warning():
    result = _result(action_type="information", highlight_rect=None)
    report = validate_vision_result(result, "screen_01")
    assert not any("'click' eylemi" in w for w in report["warnings"])


# --- Faz 4B: validate_grounded_result (grounded sonuç doğrulaması) -----------

VALID_OBSERVATION_DATA = {
    "image_id": "screen_01",
    "visible_ui_elements": ["Yolculuk kartı", "Yeni Yolculuk Ekle butonu"],
    "detected_visible_labels": ["Yeni Yolculuk Ekle"],
    "possible_primary_target": "Yeni Yolculuk Ekle",
    "preliminary_action_type": "click",
    "preliminary_highlight_rect": None,
    "confidence": 0.85,
    "visual_uncertainties": [],
}

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


@pytest.fixture(scope="module")
def real_kb():
    return load_knowledge_base()


def _grounded_result(**overrides):
    data = dict(VALID_GROUNDED_DATA)
    data.update(overrides)
    return validate_grounded_scene_result(data)


def _observation(**overrides):
    data = dict(VALID_OBSERVATION_DATA)
    data.update(overrides)
    return validate_visual_observation(data)


def test_valid_grounded_result_passes(real_kb):
    result = _grounded_result()
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert report["passed"] is True
    assert report["errors"] == []


def test_grounded_result_unknown_matched_screen_id_fails(real_kb):
    result = _grounded_result(matched_screen_id="not_a_real_screen")
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert report["passed"] is False
    assert any("onaylı bilgi tabanında bulunamadı" in e for e in report["errors"])


def test_grounded_result_no_match_produces_warning(real_kb):
    result = _grounded_result(matched_screen_id=None, matched_screen_name=None, target_element_id=None)
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert report["passed"] is True
    assert any("Ekran bilgi tabanıyla güvenilir biçimde eşleştirilemedi" in w for w in report["warnings"])


def test_grounded_result_no_match_warning_not_duplicated(real_kb):
    """run_grounded_vision_analysis, bu uyarıyı yalnızca bu fonksiyondan (tek
    kaynak olarak) alır; burada da yalnızca bir kez üretilmelidir."""
    result = _grounded_result(matched_screen_id=None, matched_screen_name=None, target_element_id=None)
    report = validate_grounded_result(result, "screen_01", real_kb)
    occurrences = [w for w in report["warnings"] if "güvenilir biçimde eşleştirilemedi" in w]
    assert len(occurrences) == 1


def test_grounded_result_target_element_not_belonging_to_matched_screen_fails(real_kb):
    # journey_create_basic ekranına ait bir öğeyi dashboard eşleşmesine bağla.
    result = _grounded_result(target_element_id="basic_next_button")
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert report["passed"] is False
    assert any("ait değil" in e for e in report["errors"])


def test_grounded_result_missing_target_for_click_action_produces_warning(real_kb):
    result = _grounded_result(target_element_id=None)
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("onaylı bir arayüz öğesi eşleşmedi" in w for w in report["warnings"])


def test_grounded_result_invalid_grounding_source_id_produces_warning(real_kb):
    result = _grounded_result(grounding_source_ids=["screen:not_a_real_screen"])
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("Geçersiz grounding kaynağı" in w for w in report["warnings"])


def test_grounded_result_unparseable_grounding_source_id_produces_warning(real_kb):
    result = _grounded_result(grounding_source_ids=["totally-invalid-format"])
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("Tanınmayan grounding kaynağı biçimi" in w for w in report["warnings"])


def test_grounded_result_expected_screen_mismatch_produces_warning(real_kb):
    result = _grounded_result()
    report = validate_grounded_result(result, "screen_01", real_kb, expected_screen_id="journeys_list")
    assert any("beklenen iş akışı adımıyla" in w for w in report["warnings"])


def test_grounded_result_low_screen_match_score_produces_warning(real_kb):
    result = _grounded_result(screen_match_score=0.3)
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("Ekran eşleşme skoru düşük" in w for w in report["warnings"])


def test_grounded_result_requires_review_false_produces_warning(real_kb):
    result = _grounded_result(requires_review=False)
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("requires_review=false" in w for w in report["warnings"])


def test_grounded_result_visual_target_conflict_produces_warning(real_kb):
    observation = _observation(possible_primary_target="Tamamen farklı bir metin")
    result = _grounded_result(target_element_id="dashboard_new_journey_button")
    report = validate_grounded_result(result, "screen_01", real_kb, observation=observation)
    assert any("hedef ile bilgi tabanındaki beklenen öğe" in w for w in report["warnings"])


def test_grounded_result_no_conflict_when_target_matches_observation(real_kb):
    observation = _observation(possible_primary_target="Yeni Yolculuk Ekle")
    result = _grounded_result(target_element_id="dashboard_new_journey_button")
    report = validate_grounded_result(result, "screen_01", real_kb, observation=observation)
    assert not any("hedef ile bilgi tabanındaki beklenen öğe" in w for w in report["warnings"])


def test_grounded_result_discouraged_terminology_produces_warning(real_kb):
    avoided_term = real_kb.terminology[0].avoid[0]
    result = _grounded_result(narration=f"Bu ekranda {avoided_term} kullanılır.")
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("Kullanılmaması gereken terim tespit edildi" in w for w in report["warnings"])


def test_grounded_result_unsupported_completion_claim_produces_warning(real_kb):
    result = _grounded_result(narration="Yolculuk başarıyla oluşturuldu ve yayınlandı.")
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert any("Kesin sonuç ifadesi tespit edildi" in w for w in report["warnings"])


def test_grounded_result_mismatched_image_id_fails(real_kb):
    result = _grounded_result(image_id="screen_02")
    report = validate_grounded_result(result, "screen_01", real_kb)
    assert report["passed"] is False
    assert any("eşleşmiyor" in e for e in report["errors"])


# --- Faz 4C: validate_scene_expansion (alt sahne genişletmesi doğrulaması) ---

VALID_SUB_SCENE = {
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
}


def _expansion_result(sub_scenes=None, **overrides):
    data = {
        "image_id": "screen_03",
        "sub_scenes": sub_scenes if sub_scenes is not None else [dict(VALID_SUB_SCENE)],
    }
    data.update(overrides)
    return validate_scene_expansion_result(data)


def test_valid_scene_expansion_passes(real_kb):
    result = _expansion_result()
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert report["passed"] is True
    assert report["errors"] == []


def test_scene_expansion_target_not_belonging_to_matched_screen_fails(real_kb):
    # dashboard_new_journey_button, journey_create_basic ekranına ait değil.
    sub_scene = dict(VALID_SUB_SCENE, target_element_id="dashboard_new_journey_button")
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert report["passed"] is False
    assert any("ait değil" in e for e in report["errors"])


def test_scene_expansion_unknown_target_element_fails(real_kb):
    sub_scene = dict(VALID_SUB_SCENE, target_element_id="totally_unknown_element")
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert report["passed"] is False
    assert any("ait değil" in e for e in report["errors"])


def test_scene_expansion_missing_target_for_action_produces_warning(real_kb):
    sub_scene = dict(VALID_SUB_SCENE, target_element_id=None)
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert any("onaylı bir arayüz öğesi eşleşmedi" in w for w in report["warnings"])


def test_scene_expansion_review_action_without_target_no_warning(real_kb):
    sub_scene = dict(VALID_SUB_SCENE, target_element_id=None, action_type="review")
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert not any("onaylı bir arayüz öğesi eşleşmedi" in w for w in report["warnings"])


def test_scene_expansion_duplicate_target_produces_warning(real_kb):
    sub2 = dict(VALID_SUB_SCENE, sub_scene_key="journey_name_again", scene_title="Tekrar")
    result = _expansion_result(sub_scenes=[dict(VALID_SUB_SCENE), sub2])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert any("birden fazla alt sahnede hedef" in w for w in report["warnings"])


def test_scene_expansion_invalid_grounding_source_id_produces_warning(real_kb):
    sub_scene = dict(VALID_SUB_SCENE, grounding_source_ids=["screen:not_a_real_screen"])
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert any("Geçersiz grounding kaynağı" in w for w in report["warnings"])


def test_scene_expansion_requires_review_false_produces_warning(real_kb):
    sub_scene = dict(VALID_SUB_SCENE, requires_review=False)
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert any("requires_review=false" in w for w in report["warnings"])


def test_scene_expansion_discouraged_terminology_produces_warning(real_kb):
    avoided_term = real_kb.terminology[0].avoid[0]
    sub_scene = dict(VALID_SUB_SCENE, narration=f"Bu ekranda {avoided_term} kullanılır.")
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert any("Kullanılmaması gereken terim tespit edildi" in w for w in report["warnings"])


def test_scene_expansion_unsupported_completion_claim_produces_warning(real_kb):
    sub_scene = dict(VALID_SUB_SCENE, narration="Yolculuk başarıyla oluşturuldu ve yayınlandı.")
    result = _expansion_result(sub_scenes=[sub_scene])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert any("Kesin sonuç ifadesi tespit edildi" in w for w in report["warnings"])


def test_scene_expansion_multiple_sub_scenes_all_valid(real_kb):
    sub1 = dict(VALID_SUB_SCENE)
    sub2 = dict(
        VALID_SUB_SCENE,
        sub_scene_key="dates",
        scene_title="Tarihleri ayarlama",
        target_element_id="basic_start_date_field",
        grounding_source_ids=["screen:journey_create_basic", "element:basic_start_date_field"],
    )
    sub3 = dict(
        VALID_SUB_SCENE,
        sub_scene_key="continue",
        scene_title="İleri ile devam etme",
        target_element_id="basic_next_button",
        action_type="click",
        grounding_source_ids=["screen:journey_create_basic", "element:basic_next_button"],
    )
    result = _expansion_result(sub_scenes=[sub1, sub2, sub3])
    report = validate_scene_expansion(result, "journey_create_basic", real_kb)
    assert report["passed"] is True
    assert report["errors"] == []
