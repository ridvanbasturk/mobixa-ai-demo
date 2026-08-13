import io

import pytest

from services.learning_path_service import (
    find_unknown_excluded_ids,
    load_and_validate_catalog,
    load_and_validate_journey_brief,
    validate_business_rules,
)

VALID_BRIEF = {
    "journey_name": "Satış ve İSG Oryantasyonu",
    "journey_type": "Private",
    "audience_description": "Yeni işe başlayan satış temsilcileri",
    "goal_description": "Temel iş güvenliği bilincini ve satış becerilerini pekiştirmek",
    "required_topics": ["Bilgi Güvenliği", "Satış"],
    "excluded_activity_ids": ["A01"],
    "min_activities": 1,
    "max_activities": 3,
    "must_end_with_test": True,
}

CATALOG_CSV = (
    "id,title,activity_type,activity_sub_type,topic,duration_minutes,question_count\n"
    "A01,Bilgi Güvenliği Kartı,LEARN,DEEPLEARN,Bilgi Güvenliği,4,10\n"
    "A02,Güçlü Parola Oyunu,GAME,DEEPLEARN,Bilgi Güvenliği,5,12\n"
    "A03,Satış Kapama Oyunu,GAME,DEEPLEARN,Satış,6,15\n"
    "A09,Final Sınavı,TEST,EXAM,Satış,7,20\n"
)


def _catalog_df():
    df, error = load_and_validate_catalog(io.StringIO(CATALOG_CSV))
    assert error is None
    return df


def test_valid_brief_passes():
    brief, error = load_and_validate_journey_brief(dict(VALID_BRIEF))
    assert error is None
    assert brief["journey_name"] == "Satış ve İSG Oryantasyonu"


def test_missing_brief_fields_reported():
    incomplete = dict(VALID_BRIEF)
    del incomplete["min_activities"]
    brief, error = load_and_validate_journey_brief(incomplete)
    assert brief is None
    assert "min_activities" in error


def test_invalid_journey_type_rejected():
    bad = dict(VALID_BRIEF, journey_type="Secret")
    brief, error = load_and_validate_journey_brief(bad)
    assert brief is None
    assert "journey_type" in error


def test_min_greater_than_max_rejected():
    bad = dict(VALID_BRIEF, min_activities=5, max_activities=2)
    brief, error = load_and_validate_journey_brief(bad)
    assert brief is None
    assert "min_activities" in error


def test_non_bool_must_end_with_test_rejected():
    bad = dict(VALID_BRIEF, must_end_with_test="yes")
    brief, error = load_and_validate_journey_brief(bad)
    assert brief is None
    assert "must_end_with_test" in error


def test_missing_catalog_columns_reported():
    df, error = load_and_validate_catalog(io.StringIO("id,title\nA01,Kart\n"))
    assert df is None
    assert "Eksik sütun" in error


def test_duplicate_catalog_ids_rejected():
    csv_text = (
        "id,title,activity_type,activity_sub_type,topic,duration_minutes,question_count\n"
        "A01,Kart 1,LEARN,DEEPLEARN,Bilgi Güvenliği,4,10\n"
        "A01,Kart 2,GAME,DEEPLEARN,Bilgi Güvenliği,5,10\n"
    )
    df, error = load_and_validate_catalog(io.StringIO(csv_text))
    assert df is None
    assert "Tekrarlanan" in error


def test_invalid_activity_type_rejected():
    csv_text = (
        "id,title,activity_type,activity_sub_type,topic,duration_minutes,question_count\n"
        "A01,Kart,QUIZ,DEEPLEARN,Bilgi Güvenliği,4,10\n"
    )
    df, error = load_and_validate_catalog(io.StringIO(csv_text))
    assert df is None
    assert "activity_type" in error


def test_invalid_duration_rejected():
    csv_text = (
        "id,title,activity_type,activity_sub_type,topic,duration_minutes,question_count\n"
        "A01,Kart,LEARN,DEEPLEARN,Bilgi Güvenliği,-3,10\n"
    )
    df, error = load_and_validate_catalog(io.StringIO(csv_text))
    assert df is None
    assert "duration_minutes" in error


def test_unknown_excluded_ids_reported_as_warning_not_crash():
    catalog_df = _catalog_df()
    brief = dict(VALID_BRIEF, excluded_activity_ids=["A01", "DOES-NOT-EXIST"])
    unknown = find_unknown_excluded_ids(brief, catalog_df)
    assert unknown == ["DOES-NOT-EXIST"]


def _activity_item(activity_id, order, estimated_minutes, reason="Gerekçe"):
    return {"activity_id": activity_id, "order": order, "reason": reason, "estimated_minutes": estimated_minutes}


def test_invented_activity_id_fails_business_validation():
    catalog_df = _catalog_df()
    activities = [_activity_item("DOES-NOT-EXIST", 1, 5)]
    result = validate_business_rules(activities, 5, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("bulunmayan aktivite" in e for e in result["errors"])


def test_excluded_activity_selected_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A03", 2, 6), _activity_item("A09", 3, 7)]
    brief = dict(VALID_BRIEF, excluded_activity_ids=["A02"])
    result = validate_business_rules(activities, 18, brief, catalog_df)
    assert result["passed"] is False
    assert any("Hariç tutulması gereken" in e for e in result["errors"])


def test_duplicate_activity_selected_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A02", 2, 5)]
    result = validate_business_rules(activities, 10, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("birden fazla kez" in e for e in result["errors"])


def test_incorrect_estimated_duration_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 999)]  # catalog says 5
    result = validate_business_rules(activities, 999, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("uyuşmuyor" in e for e in result["errors"])


def test_incorrect_total_minutes_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A03", 2, 6)]
    result = validate_business_rules(activities, 999, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("Toplam süre tutarsız" in e for e in result["errors"])


def test_too_few_activities_fails():
    catalog_df = _catalog_df()
    brief = dict(VALID_BRIEF, min_activities=2, max_activities=3)
    activities = [_activity_item("A02", 1, 5)]
    result = validate_business_rules(activities, 5, brief, catalog_df)
    assert result["passed"] is False
    assert any("minimum sınırın altında" in e for e in result["errors"])


def test_too_many_activities_fails():
    catalog_df = _catalog_df()
    brief = dict(VALID_BRIEF, min_activities=1, max_activities=1)
    activities = [_activity_item("A02", 1, 5), _activity_item("A03", 2, 6)]
    result = validate_business_rules(activities, 11, brief, catalog_df)
    assert result["passed"] is False
    assert any("maksimum sınırı aşıyor" in e for e in result["errors"])


def test_must_end_with_test_violated_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A03", 2, 6)]
    result = validate_business_rules(activities, 11, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("must_end_with_test" in e for e in result["errors"])


def test_must_end_with_test_satisfied_passes_that_rule():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A09", 2, 7)]
    result = validate_business_rules(activities, 12, VALID_BRIEF, catalog_df)
    assert not any("must_end_with_test" in e for e in result["errors"])


def test_non_consecutive_order_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A03", 3, 6)]
    result = validate_business_rules(activities, 11, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("order" in e.lower() for e in result["errors"])


def test_required_topic_coverage_reported():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A09", 2, 7)]
    result = validate_business_rules(activities, 12, VALID_BRIEF, catalog_df)
    assert result["required_topics_total"] == 2
    assert result["required_topics_covered"] == 2


def test_uncovered_required_topic_fails():
    catalog_df = _catalog_df()
    activities = [_activity_item("A09", 1, 7)]  # only covers "Satış"
    result = validate_business_rules(activities, 7, VALID_BRIEF, catalog_df)
    assert result["passed"] is False
    assert any("hiçbir aktivite ile kapsanmıyor" in e for e in result["errors"])


def test_valid_complete_journey_passes():
    catalog_df = _catalog_df()
    activities = [_activity_item("A02", 1, 5), _activity_item("A09", 2, 7)]
    result = validate_business_rules(activities, 12, VALID_BRIEF, catalog_df)
    assert result["passed"] is True
    assert result["errors"] == []
    assert result["required_topics_covered"] == 2
    assert result["required_topics_total"] == 2
    enriched_titles = {e["activity_id"]: e["title"] for e in result["enriched_path"]}
    assert enriched_titles["A02"] == "Güçlü Parola Oyunu"
