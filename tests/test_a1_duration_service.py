from services.a1_duration_service import (
    DURATION_SOURCE,
    MAX_SCENE_DURATION_SECONDS,
    MIN_SCENE_DURATION_SECONDS,
    estimate_recommended_duration,
    manual_duration_warning,
    reading_seconds_for,
)


def _narration(word_count: int) -> str:
    return " ".join(["kelime"] * word_count)


def test_click_duration_estimate_is_short():
    # 8 kelime ~ 8/2.3 = 3.48 sn okuma + click payı 2.0 = 5.48 -> 5.5 sn
    duration = estimate_recommended_duration(_narration(8), "click")
    assert 5.0 <= duration <= 7.0


def test_enter_text_duration_estimate_longer_than_click():
    click_duration = estimate_recommended_duration(_narration(8), "click")
    enter_text_duration = estimate_recommended_duration(_narration(8), "enter_text")
    assert enter_text_duration > click_duration


def test_review_duration_estimate_mid_range():
    # Uzunca bir anlatım (form açıklaması benzeri).
    duration = estimate_recommended_duration(_narration(18), "review")
    assert 7.0 <= duration <= 11.0


def test_form_explanation_duration_estimate_range():
    duration = estimate_recommended_duration(_narration(22), "enter_text")
    assert 8.0 <= duration <= 12.0


def test_duration_clamped_to_minimum():
    duration = estimate_recommended_duration("Kısa.", "information")
    assert duration == MIN_SCENE_DURATION_SECONDS


def test_duration_clamped_to_maximum():
    duration = estimate_recommended_duration(_narration(200), "enter_text")
    assert duration == MAX_SCENE_DURATION_SECONDS


def test_duration_rounded_to_nearest_half_second():
    duration = estimate_recommended_duration(_narration(8), "click")
    assert (duration * 2) == int(duration * 2)


def test_unknown_action_type_uses_default_allowance():
    duration_known = estimate_recommended_duration(_narration(8), "click")
    duration_unknown = estimate_recommended_duration(_narration(8), "unknown_action")
    assert duration_unknown >= duration_known - 0.5  # click(2.0) ve default(2.0) payı eşit


def test_duration_source_constant_value():
    assert DURATION_SOURCE == "deterministic_text_estimate"


def test_reading_seconds_for_scales_with_word_count():
    assert reading_seconds_for(_narration(23)) > reading_seconds_for(_narration(2))


def test_manual_duration_warning_when_too_short():
    narration = _narration(30)  # ~13 sn okuma
    warning = manual_duration_warning(narration, 5.0)
    assert warning is not None
    assert "kısa" in warning


def test_manual_duration_no_warning_when_sufficient():
    narration = _narration(5)
    warning = manual_duration_warning(narration, MAX_SCENE_DURATION_SECONDS)
    assert warning is None


def test_manual_duration_warning_does_not_raise_or_block():
    # Fonksiyon yalnızca bir uyarı metni/None döner; hiçbir istisna fırlatmaz.
    narration = _narration(50)
    result = manual_duration_warning(narration, MIN_SCENE_DURATION_SECONDS)
    assert isinstance(result, str)
