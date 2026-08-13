import pytest
from pydantic import ValidationError

from schemas.c1_models import validate_c1_output

VALID_ACTIVITY = {
    "activity_id": "A02",
    "order": 1,
    "reason": "Zorunlu konuyu kapsar.",
    "estimated_minutes": 5,
}


def _make_data(
    activities,
    total_minutes=None,
    audience_fit_summary="Hedef kitle özeti.",
    strategy_summary="Strateji özeti.",
):
    if total_minutes is None:
        total_minutes = sum(a["estimated_minutes"] for a in activities)
    return {
        "audience_fit_summary": audience_fit_summary,
        "recommended_activities": activities,
        "total_minutes": total_minutes,
        "strategy_summary": strategy_summary,
    }


def test_valid_output_passes():
    activities = [
        dict(VALID_ACTIVITY, activity_id="A02", order=1),
        dict(VALID_ACTIVITY, activity_id="A03", order=2, estimated_minutes=4),
    ]
    data = _make_data(activities)
    result = validate_c1_output(data)
    assert len(result.recommended_activities) == 2
    assert result.total_minutes == 9


def test_empty_recommended_activities_fails():
    data = _make_data([], total_minutes=1)
    with pytest.raises(ValueError):
        validate_c1_output(data)


def test_duplicate_activity_ids_fail():
    activities = [
        dict(VALID_ACTIVITY, activity_id="A02", order=1),
        dict(VALID_ACTIVITY, activity_id="A02", order=2),
    ]
    data = _make_data(activities)
    with pytest.raises(ValueError):
        validate_c1_output(data)


def test_duplicate_order_values_fail():
    activities = [
        dict(VALID_ACTIVITY, activity_id="A02", order=1),
        dict(VALID_ACTIVITY, activity_id="A03", order=1),
    ]
    data = _make_data(activities)
    with pytest.raises(ValueError):
        validate_c1_output(data)


def test_non_consecutive_order_fails():
    activities = [
        dict(VALID_ACTIVITY, activity_id="A02", order=1),
        dict(VALID_ACTIVITY, activity_id="A03", order=3),
    ]
    data = _make_data(activities)
    with pytest.raises(ValueError):
        validate_c1_output(data)


def test_order_not_starting_at_one_fails():
    activities = [
        dict(VALID_ACTIVITY, activity_id="A02", order=2),
        dict(VALID_ACTIVITY, activity_id="A03", order=3),
    ]
    data = _make_data(activities)
    with pytest.raises(ValueError):
        validate_c1_output(data)


def test_blank_reason_fails():
    activities = [dict(VALID_ACTIVITY, reason="   ")]
    data = _make_data(activities)
    with pytest.raises(ValidationError):
        validate_c1_output(data)


def test_non_positive_estimated_minutes_fails():
    activities = [dict(VALID_ACTIVITY, estimated_minutes=0)]
    data = _make_data(activities, total_minutes=0)
    with pytest.raises(ValidationError):
        validate_c1_output(data)


def test_non_positive_total_minutes_fails():
    activities = [dict(VALID_ACTIVITY)]
    data = _make_data(activities, total_minutes=0)
    with pytest.raises(ValidationError):
        validate_c1_output(data)


def test_blank_audience_fit_summary_fails():
    activities = [dict(VALID_ACTIVITY)]
    data = _make_data(activities, audience_fit_summary="")
    with pytest.raises(ValidationError):
        validate_c1_output(data)
