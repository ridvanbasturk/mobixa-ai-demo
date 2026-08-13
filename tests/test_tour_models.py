import pytest
from pydantic import ValidationError

from schemas.tour_models import (
    ACTION_CLICK,
    ACTION_DONE,
    ALLOWED_ACTIONS,
    TourElement,
    TourRecording,
    TourStep,
    validate_tour_decision,
)


def _decision(**overrides):
    data = {
        "action": "click",
        "element_index": 3,
        "narration": "Şimdi Journey üretimini başlatıyorum.",
        "reason": "Ana eylemi göstermek için.",
    }
    data.update(overrides)
    return data


def test_valid_decision_passes():
    decision = validate_tour_decision(_decision())
    assert decision.action == ACTION_CLICK
    assert decision.element_index == 3
    assert not decision.is_done


def test_unknown_action_rejected():
    with pytest.raises(ValidationError):
        validate_tour_decision(_decision(action="navigate_to_url"))


def test_action_is_normalized_to_lowercase():
    decision = validate_tour_decision(_decision(action="CLICK"))
    assert decision.action == ACTION_CLICK


def test_blank_narration_rejected():
    with pytest.raises(ValidationError):
        validate_tour_decision(_decision(narration="   "))


def test_done_decision_needs_no_element():
    decision = validate_tour_decision(
        {"action": "done", "narration": "Tur tamamlandı.", "element_index": None}
    )
    assert decision.is_done
    assert decision.action == ACTION_DONE


def test_allowed_actions_are_deliberately_narrow():
    # Tarayıcıda keyfi gezinme/kod çalıştırma bilinçli olarak YOKTUR.
    assert "navigate" not in ALLOWED_ACTIONS
    assert "evaluate" not in ALLOWED_ACTIONS
    assert ALLOWED_ACTIONS == {"click", "type", "scroll_to", "highlight", "wait", "done"}


def test_element_center_and_description():
    element = TourElement(
        index=2, role="button", name="Turu Çek", key="a1_record", x=10, y=20, width=100, height=40
    )
    assert element.center == (60, 40)
    described = element.describe()
    assert "[2]" in described
    assert "Turu Çek" in described
    assert "key=a1_record" in described
    assert "main" in described


def test_disabled_element_is_described_as_disabled():
    element = TourElement(
        index=1, role="button", name="Kapalı", x=0, y=0, width=50, height=20, enabled=False
    )
    assert "(disabled)" in element.describe()


def test_step_end_seconds():
    step = TourStep(
        index=1,
        action="click",
        narration="…",
        start_seconds=4.0,
        duration_seconds=2.5,
    )
    assert step.end_seconds == 6.5


def test_recording_step_count():
    recording = TourRecording(
        module="c1",
        language="tr",
        model_id="google.gemma-4-31b",
        steps=[
            TourStep(index=1, action="wait", narration="a", start_seconds=0, duration_seconds=1),
            TourStep(index=2, action="click", narration="b", start_seconds=1, duration_seconds=1),
        ],
    )
    assert recording.step_count == 2
