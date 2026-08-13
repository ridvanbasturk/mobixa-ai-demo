import io

import pandas as pd
import pytest

from services.report_service import (
    compute_report_metrics,
    load_and_validate_report,
    validate_numeric_grounding,
)


def _sample_df():
    csv_text = (
        "user_group,journey,completion_rate,quiz_score,inactive_days,active_users\n"
        "Satış,Yeni Çalışan Oryantasyonu,42,58,9,120\n"
        "Yazılım,Bilgi Güvenliği,88,81,2,95\n"
        "İnsan Kaynakları,KVKK Farkındalık,63,73,5,85\n"
    )
    df, error = load_and_validate_report(io.StringIO(csv_text))
    assert error is None
    return df


def test_weighted_completion_rate():
    df = _sample_df()
    metrics = compute_report_metrics(df, "2026 Q2")
    expected = round((42 * 120 + 88 * 95 + 63 * 85) / (120 + 95 + 85), 1)
    assert metrics["overall_completion_rate"] == expected


def test_weighted_quiz_score():
    df = _sample_df()
    metrics = compute_report_metrics(df, "2026 Q2")
    expected = round((58 * 120 + 81 * 95 + 73 * 85) / (120 + 95 + 85), 1)
    assert metrics["overall_average_quiz_score"] == expected


def test_lowest_highest_groups():
    df = _sample_df()
    metrics = compute_report_metrics(df, "2026 Q2")
    assert metrics["lowest_completion_group"] == "Satış — Yeni Çalışan Oryantasyonu"
    assert metrics["highest_completion_group"] == "Yazılım — Bilgi Güvenliği"
    assert metrics["lowest_quiz_group"] == "Satış — Yeni Çalışan Oryantasyonu"
    assert metrics["highest_quiz_group"] == "Yazılım — Bilgi Güvenliği"


def test_risk_code_generation():
    df = _sample_df()
    metrics = compute_report_metrics(df, "2026 Q2")
    by_group = {g["group"]: g["risk_codes"] for g in metrics["group_metrics"]}

    # completion_rate=42 (<50), quiz_score=58 (<60), inactive_days=9 (>7)
    assert set(by_group["Satış — Yeni Çalışan Oryantasyonu"]) == {
        "completion_below_50",
        "quiz_score_below_60",
        "inactive_days_above_7",
    }
    # completion_rate=88, quiz_score=81, inactive_days=2 -> no risk codes
    assert by_group["Yazılım — Bilgi Güvenliği"] == []
    # completion_rate=63 (50<=x<70), quiz_score=73, inactive_days=5 (4<x<=7)
    assert set(by_group["İnsan Kaynakları — KVKK Farkındalık"]) == {
        "completion_below_70",
        "inactive_days_above_4",
    }

    risk_group_labels = {rg["group"] for rg in metrics["risk_groups"]}
    assert risk_group_labels == {
        "Satış — Yeni Çalışan Oryantasyonu",
        "İnsan Kaynakları — KVKK Farkındalık",
    }


def test_missing_columns_returns_turkish_error():
    csv_text = "user_group,journey,completion_rate\nSatış,Oryantasyon,50\n"
    df, error = load_and_validate_report(io.StringIO(csv_text))
    assert df is None
    assert error is not None
    assert "Eksik sütun" in error


def test_invalid_numeric_data_returns_turkish_error():
    csv_text = (
        "user_group,journey,completion_rate,quiz_score,inactive_days,active_users\n"
        "Satış,Oryantasyon,elli,58,9,120\n"
    )
    df, error = load_and_validate_report(io.StringIO(csv_text))
    assert df is None
    assert error is not None
    assert "geçersiz veri" in error.lower()


def test_zero_active_users_raises_value_error():
    csv_text = (
        "user_group,journey,completion_rate,quiz_score,inactive_days,active_users\n"
        "Satış,Oryantasyon,50,60,3,0\n"
    )
    df, error = load_and_validate_report(io.StringIO(csv_text))
    assert error is None
    with pytest.raises(ValueError):
        compute_report_metrics(df, "2026 Q2")


def test_numeric_validation_accepts_matching_numbers_with_turkish_comma():
    metrics = {"overall_completion_rate": 42.5, "total_active_users": 120}
    insights = [
        {
            "title": "Tamamlama oranı düşük (99.9)",
            "finding": "Genel tamamlama oranı 42,5 seviyesinde.",
            "evidence": "Toplam aktif kullanıcı 120.",
        }
    ]
    passed, warnings = validate_numeric_grounding(insights, metrics)
    assert passed is True
    assert warnings == []


def test_numeric_validation_flags_unknown_numbers():
    metrics = {"overall_completion_rate": 42.5, "total_active_users": 120}
    insights = [
        {
            "title": "Başlık",
            "finding": "Tamamlama oranı 99 seviyesinde.",
            "evidence": "Aktif kullanıcı 120.",
        }
    ]
    passed, warnings = validate_numeric_grounding(insights, metrics)
    assert passed is False
    assert "99" in warnings


def test_numeric_validation_treats_int_and_float_as_equal():
    metrics = {"total_active_users": 120}
    insights = [{"title": "x", "finding": "120.0 kullanıcı var.", "evidence": ""}]
    passed, warnings = validate_numeric_grounding(insights, metrics)
    assert passed is True
    assert warnings == []
