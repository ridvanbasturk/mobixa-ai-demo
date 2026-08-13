"""A1 Ürün Bilgi Tabanı için AWS'den bağımsız testler.

Hiçbir vektör veritabanı, embedding veya ücretli servis kullanılmaz;
yalnızca yerel JSON dosyaları ve deterministik eşleştirme test edilir.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from schemas.a1_knowledge_models import validate_knowledge_base
from services.a1_knowledge_service import (
    DEFAULT_KB_DIR,
    KnowledgeBaseLoadError,
    build_grounding_context,
    get_screen,
    get_ui_elements_for_screen,
    get_workflow,
    get_workflow_step,
    load_knowledge_base,
    match_screen,
    match_target_element,
    search_by_visible_labels,
)

VALID_SCREEN = {
    "screen_id": "screen_a",
    "screen_name": "Ekran A",
    "product_area": "Test Alanı",
    "purpose": "Test amaçlı ekran.",
    "visible_labels": ["Etiket 1", "Etiket 2"],
    "supported_roles": ["Trainer"],
    "workflow_ids": [],
    "product_version": "1.0.0",
    "status": "approved",
    "last_updated": "2026-07-28",
}

VALID_ELEMENT = {
    "element_id": "element_a",
    "screen_id": "screen_a",
    "visible_label": "Etiket 1",
    "element_type": "button",
    "purpose": "Test amaçlı buton.",
    "action_type": "click",
    "result_screen_id": None,
    "prerequisites": [],
    "notes": "",
    "product_version": "1.0.0",
    "status": "approved",
}

VALID_WORKFLOW = {
    "workflow_id": "workflow_a",
    "title": "Test İş Akışı",
    "purpose": "Test amaçlı iş akışı.",
    "supported_roles": ["Trainer"],
    "product_version": "1.0.0",
    "status": "approved",
    "steps": [
        {
            "step_id": "workflow_a_01",
            "order": 1,
            "screen_id": "screen_a",
            "target_element_id": "element_a",
            "instruction": "Etiket 1'e tıklayın.",
            "expected_next_screen_id": None,
        }
    ],
}


def _kb_dict(screens=None, ui_elements=None, workflows=None, terminology=None):
    return {
        "screens": screens if screens is not None else [dict(VALID_SCREEN)],
        "ui_elements": ui_elements if ui_elements is not None else [dict(VALID_ELEMENT)],
        "workflows": workflows if workflows is not None else [json.loads(json.dumps(VALID_WORKFLOW))],
        "terminology": terminology if terminology is not None else [],
    }


# --- Pydantic doğrulama -------------------------------------------------------


def test_valid_full_knowledge_base_passes():
    kb = validate_knowledge_base(_kb_dict())
    assert len(kb.screens) == 1
    assert len(kb.ui_elements) == 1
    assert len(kb.workflows) == 1


def test_duplicate_screen_id_fails():
    screens = [dict(VALID_SCREEN), dict(VALID_SCREEN)]
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(screens=screens))


def test_duplicate_ui_element_id_fails():
    elements = [dict(VALID_ELEMENT), dict(VALID_ELEMENT)]
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(ui_elements=elements))


def test_missing_referenced_screen_in_ui_element_fails():
    element = dict(VALID_ELEMENT, screen_id="does_not_exist")
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(ui_elements=[element]))


def test_missing_referenced_result_screen_fails():
    element = dict(VALID_ELEMENT, result_screen_id="does_not_exist")
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(ui_elements=[element]))


def test_missing_referenced_ui_element_in_workflow_step_fails():
    workflow = json.loads(json.dumps(VALID_WORKFLOW))
    workflow["steps"][0]["target_element_id"] = "does_not_exist"
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(workflows=[workflow]))


def test_missing_referenced_screen_in_workflow_step_fails():
    workflow = json.loads(json.dumps(VALID_WORKFLOW))
    workflow["steps"][0]["screen_id"] = "does_not_exist"
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(workflows=[workflow]))


def test_missing_expected_next_screen_fails():
    workflow = json.loads(json.dumps(VALID_WORKFLOW))
    workflow["steps"][0]["expected_next_screen_id"] = "does_not_exist"
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(workflows=[workflow]))


def test_invalid_workflow_order_not_starting_at_one_fails():
    workflow = json.loads(json.dumps(VALID_WORKFLOW))
    workflow["steps"][0]["order"] = 2
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(workflows=[workflow]))


def test_invalid_workflow_order_non_consecutive_fails():
    workflow = json.loads(json.dumps(VALID_WORKFLOW))
    workflow["steps"].append(
        {
            "step_id": "workflow_a_03",
            "order": 3,
            "screen_id": "screen_a",
            "target_element_id": "element_a",
            "instruction": "Başka bir adım.",
            "expected_next_screen_id": None,
        }
    )
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(workflows=[workflow]))


def test_duplicate_visible_labels_within_screen_fails():
    screen = dict(VALID_SCREEN, visible_labels=["Etiket 1", "Etiket 1"])
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(screens=[screen]))


def test_invalid_element_type_fails():
    element = dict(VALID_ELEMENT, element_type="invalid_type")
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(ui_elements=[element]))


def test_invalid_action_type_fails():
    element = dict(VALID_ELEMENT, action_type="delete")
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(ui_elements=[element]))


def test_blank_product_version_fails():
    screen = dict(VALID_SCREEN, product_version="")
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(screens=[screen]))


def test_screen_workflow_ids_must_reference_existing_workflow():
    screen = dict(VALID_SCREEN, workflow_ids=["does_not_exist"])
    with pytest.raises(ValidationError):
        validate_knowledge_base(_kb_dict(screens=[screen]))


# --- Onaylı olmayan kayıtların retrieval'dan dışlanması -----------------------


def test_non_approved_screen_excluded_from_get_screen():
    screen = dict(VALID_SCREEN, status="draft")
    kb = validate_knowledge_base(_kb_dict(screens=[screen], ui_elements=[], workflows=[]))
    assert get_screen(kb, "screen_a") is None


def test_non_approved_ui_element_excluded():
    element = dict(VALID_ELEMENT, status="draft")
    kb = validate_knowledge_base(_kb_dict(ui_elements=[element], workflows=[]))
    assert get_ui_elements_for_screen(kb, "screen_a") == []


def test_non_approved_workflow_excluded():
    workflow = json.loads(json.dumps(VALID_WORKFLOW))
    workflow["status"] = "deprecated"
    kb = validate_knowledge_base(_kb_dict(workflows=[workflow]))
    assert get_workflow(kb, "workflow_a") is None


def test_non_approved_screen_excluded_from_matching():
    screen = dict(VALID_SCREEN, status="draft")
    kb = validate_knowledge_base(_kb_dict(screens=[screen], ui_elements=[], workflows=[]))
    result = match_screen(kb, ["Etiket 1"])
    assert result["matched_screen_id"] is None
    assert result["candidate_screens"] == []


# --- Basit erişimciler ---------------------------------------------------------


def test_get_workflow_step_returns_correct_step():
    kb = validate_knowledge_base(_kb_dict())
    step = get_workflow_step(kb, "workflow_a", 1)
    assert step is not None
    assert step.step_id == "workflow_a_01"


def test_get_workflow_step_missing_order_returns_none():
    kb = validate_knowledge_base(_kb_dict())
    assert get_workflow_step(kb, "workflow_a", 99) is None


def test_search_by_visible_labels_ranks_by_overlap():
    screens = [
        dict(VALID_SCREEN, screen_id="s1", visible_labels=["A", "B", "C"]),
        dict(VALID_SCREEN, screen_id="s2", visible_labels=["A"]),
    ]
    kb = validate_knowledge_base(_kb_dict(screens=screens, ui_elements=[], workflows=[]))
    results = search_by_visible_labels(kb, ["A", "B"])
    assert [s.screen_id for s in results] == ["s1", "s2"]


# --- Gerçek Mobixa bilgi tabanıyla ekran eşleştirme ----------------------------


@pytest.fixture(scope="module")
def real_kb():
    return load_knowledge_base()


def test_real_kb_loads_and_validates(real_kb):
    assert len(real_kb.screens) == 6
    assert len(real_kb.workflows) == 1


def test_exact_visible_label_match_journeys_list(real_kb):
    result = match_screen(real_kb, ["Yolculuk Ekle", "Durum", "Dışa aktar"])
    assert result["matched_screen_id"] == "journeys_list"
    assert result["score"] >= 0.65


def test_exact_visible_label_match_basic_info(real_kb):
    result = match_screen(real_kb, ["Yolculuk Adı", "Başlangıç Tarihi", "İleri"])
    assert result["matched_screen_id"] == "journey_create_basic"


def test_exact_visible_label_match_participants(real_kb):
    result = match_screen(real_kb, ["Kullanıcılar", "Gruplar", "E-posta ile ekle"])
    assert result["matched_screen_id"] == "journey_create_participants"


def test_normalized_turkish_label_match_case_insensitive(real_kb):
    # Büyük/küçük harf ve İ/I farkına rağmen eşleşmeli.
    result = match_screen(real_kb, ["yolculuk ekle", "DURUM", "dışa AKTAR"])
    assert result["matched_screen_id"] == "journeys_list"


def test_ambiguous_screen_matching_produces_warning(real_kb):
    # "İleri" tek başına üç sihirbaz ekranında da bulunur (basic/activities/participants).
    result = match_screen(real_kb, ["İleri"])
    assert any("belirsiz" in w for w in result["warnings"]) or result["matched_screen_id"] is None


def test_low_confidence_no_match_behavior(real_kb):
    result = match_screen(real_kb, ["Bilinmeyen Etiket XYZ"])
    assert result["matched_screen_id"] is None
    assert any("eşik" in w for w in result["warnings"])


def test_workflow_aware_ranking_disambiguates(real_kb):
    # "İleri" tek başına belirsiz olsa da, workflow + beklenen sıra ile
    # doğru ekrana yönlendirilmelidir.
    result_without_context = match_screen(real_kb, ["İleri"])
    result_with_context = match_screen(
        real_kb, ["İleri"], workflow_id="create_journey", expected_order=3
    )
    assert result_with_context["score"] >= result_without_context["score"]
    assert result_with_context["matched_screen_id"] == "journey_create_basic"


def test_expected_order_ranking_selects_correct_screen(real_kb):
    result = match_screen(
        real_kb, ["Geri"], workflow_id="create_journey", expected_order=4
    )
    # 4. adım journey_create_activities ekranındadır.
    assert result["matched_screen_id"] == "journey_create_activities"


# --- Grounding context ---------------------------------------------------------


def test_grounding_context_is_compact_and_relevant(real_kb):
    context = build_grounding_context(real_kb, "journeys_list", workflow_id="create_journey", step_order=2)
    assert context["screen_id"] == "journeys_list"
    assert context["screen_name"]
    assert "Yolculuk Ekle" in context["visible_labels"]
    assert context["workflow"]["workflow_id"] == "create_journey"
    assert context["current_step"]["order"] == 2
    assert context["previous_step"]["order"] == 1
    assert context["next_step"]["order"] == 3


def test_grounding_context_excludes_unrelated_screens(real_kb):
    context = build_grounding_context(real_kb, "dashboard")
    element_labels = {e["visible_label"] for e in context["ui_elements"]}
    # journeys_list'e özgü bir öğe (Sütunlar) dashboard bağlamında olmamalı.
    assert "Sütunlar" not in element_labels
    assert "Yeni Yolculuk Ekle" in element_labels


def test_grounding_context_unknown_screen_returns_none(real_kb):
    assert build_grounding_context(real_kb, "does_not_exist") is None


def test_grounding_context_includes_terminology(real_kb):
    context = build_grounding_context(real_kb, "dashboard")
    canon_terms = {t["canonical"] for t in context["terminology"]}
    assert "öğrenme yolculuğu" in canon_terms


def test_terminology_lookup_contains_avoid_terms(real_kb):
    entry = next(t for t in real_kb.terminology if t.canonical == "aktivite")
    assert "içerik öğesi" in entry.avoid


# --- Faz 4C: daha toleranslı etiket normalizasyonu -----------------------------


def test_normalize_label_strips_plus_prefix():
    from services.a1_knowledge_service import _normalize_label

    assert _normalize_label("+ Yeni Yolculuk Ekle") == _normalize_label("Yeni Yolculuk Ekle")
    assert _normalize_label("+ Yolculuk Ekle") == _normalize_label("Yolculuk Ekle")


def test_normalize_label_preserves_internal_dash():
    from services.a1_knowledge_service import _normalize_label

    assert _normalize_label("E-posta ile ekle") == _normalize_label("E-posta ile ekle")
    assert "posta" in _normalize_label("E-posta ile ekle")


def test_normalize_label_case_insensitive_turkish():
    from services.a1_knowledge_service import _normalize_label

    assert _normalize_label("Oluştur ve Hemen Başlat") == _normalize_label("Oluştur ve hemen başlat")


def test_normalize_label_strips_trailing_arrow_and_punctuation():
    from services.a1_knowledge_service import _normalize_label

    assert _normalize_label("İleri >") == _normalize_label("İleri")
    assert _normalize_label("Vazgeç:") == _normalize_label("Vazgeç")


def test_normalize_label_collapses_duplicate_whitespace():
    from services.a1_knowledge_service import _normalize_label

    assert _normalize_label("Yeni   Yolculuk    Ekle") == _normalize_label("Yeni Yolculuk Ekle")


def test_normalize_label_does_not_remove_meaningful_words():
    from services.a1_knowledge_service import _normalize_label

    # Önek/noktalama temizliği, anlamlı hiçbir kelimeyi silmemeli.
    assert _normalize_label("+ Yeni Yolculuk Ekle") == "yeni yolculuk ekle"


# --- Faz 4C: gerçek (gürültülü) görsel analiz tespitleriyle ekran eşleştirme ---
# Faz 4B'nin gerçek doğrulamasında qwen.qwen3-vl-235b-a22b-instruct modeli,
# KB'nin curated visible_labels listesinde bulunmayan onlarca ek alt menü/
# sayaç etiketi de bildirdiği için bu üç ekran eşik değerinin altında
# kalmıştı. Bu testler, iyileştirilmiş overlap-coefficient tabanlı skorlama
# ve önek normalizasyonuyla artık eşik üstünde eşleştiklerini kanıtlar.

REAL_DASHBOARD_DETECTED_LABELS = [
    "Mobixa.ai", "Yönetim / Ana Sayfa", "Ana Sayfa", "Kullanıcılar", "Kullanıcı Listesi",
    "Gruplar", "İçerikler", "Sorular", "Kategoriler", "Görseller", "Videolar", "Aktiviteler",
    "Tüm Aktiviteler", "Öğrenme Kartları", "Bilgi Oyunları", "Testler", "Yolculuklar", "Raporlar",
    "Mobixa.ai Yönetim Paneline Hoş Geldiniz", "Rıdvan, bugün ne yapmak istersiniz?", "Kullanıcı",
    "Mevcut kullanıcı sayısı: 57 / 10.000", "+ Yeni Kullanıcı Ekle", "Grup",
    "Mevcut grup sayısı: 8", "+ Yeni Grup Ekle", "Soru", "Kendi Sorularınız",
    "Paylaşılan Sorular", "4.757", "+ Yeni Soru Ekle", "Kategori", "Kendi Kategorileriniz",
    "Paylaşılan Kategoriler", "Main / Sub / Subcategory", "23/63/207", "0/0/0",
    "+ Yeni Kategori Ekle", "Aktivite", "Mevcut aktivite sayısı: 37", "+ Yeni Aktivite Ekle",
    "Yolculuk", "Mevcut yolculuk sayısı: 43", "+ Yeni Yolculuk Ekle", "Mobixa nasıl kullanılır",
]

REAL_JOURNEYS_LIST_DETECTED_LABELS = [
    "Mobixa.ai", "Ana Sayfa", "Kullanıcılar", "Kullanıcı Listesi", "Gruplar", "İçerikler",
    "Sorular", "Kategoriler", "Görseller", "Videolar", "Aktiviteler", "Tüm Aktiviteler",
    "Öğrenme Kartları", "Bilgi Oyunları", "Testler", "Yolculuklar", "Raporlar", "+ Yolculuk Ekle",
    "Yolculuk adı...", "Tip seçin...", "Durum seçin...", "Yolculuk Adı", "Tip", "Durum",
    "Aktiviteler", "Atanan Kullanıcılar", "Başlangıç Tarihi", "Bitiş Tarihi",
    "Oluşturulma Tarihi", "İşlemler", "Sütunlar", "Dışa aktar", "Temizle",
]

REAL_PARTICIPANTS_DETECTED_LABELS = [
    "Yolculuk Ekle", "Temel Bilgiler", "Aktiviteler", "Katılımcılar", "Özet ve Yayınlama",
    "Yolculuk Erişimi", "Herkese Açık", "Kullanıcılar", "Gruplar", "+ Kullanıcı Seç",
    "E-posta ile ekle", "Ekle", "Ara...", "Tümünü Kaldır", "İSİM", "E-POSTA",
    "Rıdvan Baştürk", "zekiridvanbasturk2@gmail.com", "1 kayıttan 1-1 arası gösteriliyor",
    "Sayfa 1 / 1", "Önceki", "Sonraki", "Vazgeç", "Taslak olarak kaydet", "Geri", "İleri",
]


def test_real_noisy_dashboard_detection_now_matches_above_threshold(real_kb):
    result = match_screen(real_kb, REAL_DASHBOARD_DETECTED_LABELS, workflow_id="create_journey", expected_order=1)
    assert result["matched_screen_id"] == "dashboard"
    assert result["score"] >= 0.65


def test_real_noisy_journeys_list_detection_now_matches_above_threshold(real_kb):
    result = match_screen(
        real_kb, REAL_JOURNEYS_LIST_DETECTED_LABELS, workflow_id="create_journey", expected_order=2
    )
    assert result["matched_screen_id"] == "journeys_list"
    assert result["score"] >= 0.65


def test_real_noisy_participants_detection_now_matches_above_threshold(real_kb):
    result = match_screen(
        real_kb, REAL_PARTICIPANTS_DETECTED_LABELS, workflow_id="create_journey", expected_order=5
    )
    assert result["matched_screen_id"] == "journey_create_participants"
    assert result["score"] >= 0.65


# --- Faz 4B: deterministik hedef (target) öğe eşleştirmesi ---------------------


def test_exact_target_match_dashboard_new_journey_button(real_kb):
    result = match_target_element(real_kb, "dashboard", "Yeni Yolculuk Ekle")
    assert result["target_element_id"] == "dashboard_new_journey_button"
    assert result["target_match_score"] == pytest.approx(1.0)
    assert result["target_match_warnings"] == []


def test_target_match_unknown_label_returns_none(real_kb):
    result = match_target_element(real_kb, "dashboard", "Tamamen uydurma bir buton")
    assert result["target_element_id"] is None
    assert result["target_match_warnings"] != []


def test_target_match_blank_label_returns_none_with_warning(real_kb):
    result = match_target_element(real_kb, "dashboard", "")
    assert result["target_element_id"] is None
    assert "Karşılaştırılacak bir hedef etiketi verilmedi." in result["target_match_warnings"][0]


def test_target_match_unknown_screen_returns_none_with_warning(real_kb):
    result = match_target_element(real_kb, "does_not_exist", "Yeni Yolculuk Ekle")
    assert result["target_element_id"] is None
    assert any("onaylı arayüz öğesi bulunamadı" in w for w in result["target_match_warnings"])


def test_target_match_belongs_to_requested_screen_only(real_kb):
    # "İleri" journey_create_basic ekranında var; dashboard'da eşleşmemeli.
    result = match_target_element(real_kb, "dashboard", "İleri")
    assert result["target_element_id"] is None


# --- Dosya yükleme hataları -----------------------------------------------------


def test_missing_knowledge_base_file_raises_clear_error(tmp_path):
    with pytest.raises(KnowledgeBaseLoadError):
        load_knowledge_base(tmp_path)


def test_malformed_json_raises_clear_error(tmp_path):
    (tmp_path / "screens.json").write_text("{not valid json", encoding="utf-8")
    (tmp_path / "ui_elements.json").write_text("[]", encoding="utf-8")
    (tmp_path / "workflows.json").write_text("[]", encoding="utf-8")
    (tmp_path / "terminology.json").write_text('{"approved_terms": []}', encoding="utf-8")

    with pytest.raises(KnowledgeBaseLoadError):
        load_knowledge_base(tmp_path)


def test_default_kb_dir_points_to_sample_data():
    assert DEFAULT_KB_DIR.name == "knowledge_base"
    assert (DEFAULT_KB_DIR / "screens.json").exists()
