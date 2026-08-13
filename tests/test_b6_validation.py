import pytest
from pydantic import ValidationError

from schemas.b6_models import validate_b6_output

INSIGHT_TEMPLATE = {
    "finding": "Bulgu metni.",
    "evidence": "Kanıt metni.",
    "recommendation": "Öneri metni.",
    "severity": "low",
}


def _make_insight(title: str, **overrides):
    insight = dict(INSIGHT_TEMPLATE, title=title)
    insight.update(overrides)
    return insight


def _make_data(insights, executive_summary="Yönetici özeti."):
    return {"executive_summary": executive_summary, "insights": insights}


def test_valid_output_with_exactly_four_insights_passes():
    data = _make_data([_make_insight(f"Başlık {i}") for i in range(4)])
    result = validate_b6_output(data)
    assert len(result.insights) == 4


def test_fewer_than_four_insights_fails():
    data = _make_data([_make_insight(f"Başlık {i}") for i in range(3)])
    with pytest.raises(ValueError):
        validate_b6_output(data)


def test_more_than_four_insights_fails():
    data = _make_data([_make_insight(f"Başlık {i}") for i in range(5)])
    with pytest.raises(ValueError):
        validate_b6_output(data)


def test_invalid_severity_fails():
    insights = [_make_insight(f"Başlık {i}") for i in range(4)]
    insights[0]["severity"] = "critical"
    data = _make_data(insights)
    with pytest.raises(ValidationError):
        validate_b6_output(data)


def test_duplicate_titles_fail():
    insights = [_make_insight("Aynı Başlık") for _ in range(4)]
    data = _make_data(insights)
    with pytest.raises(ValueError):
        validate_b6_output(data)


def test_blank_field_fails():
    insights = [_make_insight(f"Başlık {i}") for i in range(4)]
    insights[0]["finding"] = "   "
    data = _make_data(insights)
    with pytest.raises(ValidationError):
        validate_b6_output(data)


def test_blank_executive_summary_fails():
    data = _make_data([_make_insight(f"Başlık {i}") for i in range(4)], executive_summary="")
    with pytest.raises(ValidationError):
        validate_b6_output(data)
