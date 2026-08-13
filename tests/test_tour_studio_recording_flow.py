"""Stüdyo sayfasındaki "Turu Çek" butonunun uçtan uca ARAYÜZ akışı.

`run_tour` sahte bir fonksiyonla değiştirilir: tarayıcı açılmaz, model
çağrılmaz, para harcanmaz — ama butonun gerçekten kaydı başlattığı, ilerleme
bildirimlerinin gösterildiği ve sonucun ekrana geldiği doğrulanır.

Bu test, "uygulamayı açıp butona basınca video üretilir mi?" sorusunun
regresyon güvencesidir.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from schemas.tour_models import TourRecording, TourStep

PAGE = "app_pages/a1_tour_studio.py"


def _fake_recording(tmp_video, tmp_srt) -> TourRecording:
    return TourRecording(
        module="c1",
        language="tr",
        model_id="google.gemma-4-31b",
        steps=[
            TourStep(
                index=1,
                action="click",
                element_name="İki Modelle Journey Üret",
                narration="Journey üretimini başlatıyorum.",
                reason="Sayfanın asıl eylemi.",
                start_seconds=0.0,
                duration_seconds=4.0,
            )
        ],
        video_path=str(tmp_video),
        subtitle_path=str(tmp_srt),
        total_seconds=42.0,
        voiced=False,
        voice_unavailable_reason="boto3 kurulu değil.",
        total_cost_usd=0.0031,
        stopped_reason="Ajan turu tamamladı.",
    )


@pytest.fixture
def studio(tmp_path, monkeypatch):
    """Sahte bir kayıt üreten stüdyo sayfası."""
    video = tmp_path / "c1_tr.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-video-bytes")
    srt = tmp_path / "c1_tr.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:04,000\nJourney üretimini başlatıyorum.\n", encoding="utf-8")

    calls = {}

    def fake_run_tour(**kwargs):
        calls.update(kwargs)
        # İlerleme geri çağrısı gerçekten çalışıyor mu?
        callback = kwargs.get("progress_callback")
        if callback is not None:
            from services.tour_pipeline import TourProgress

            callback(TourProgress(stage="server", message="Uygulama başlatılıyor..."))
            callback(
                TourProgress(
                    stage="acting",
                    step_index=1,
                    message="İki Modelle Journey Üret",
                    narration="Journey üretimini başlatıyorum.",
                )
            )
        return _fake_recording(video, srt)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setattr("services.tour_pipeline.run_tour", fake_run_tour)
    return calls


def _press_record(at: AppTest) -> AppTest:
    button = next(b for b in at.button if b.key == "a1_record")
    return button.click().run(timeout=60)


def test_record_button_exists_and_page_is_ready():
    at = AppTest.from_file(PAGE)
    at.run(timeout=60)
    assert at.exception == []
    assert any(b.key == "a1_record" for b in at.button)


def test_settings_are_passed_through_to_the_pipeline(studio):
    """Arayüzdeki modül/dil/adım seçimleri gerçekten boru hattına gidiyor mu?"""
    at = AppTest.from_file(PAGE)
    at.run(timeout=60)

    at.selectbox(key="a1_module").set_value("c1")
    at.selectbox(key="a1_tour_language").set_value("tr")
    at.number_input(key="a1_max_steps").set_value(9)
    at.run(timeout=60)

    _press_record(at)

    assert studio["module"] == "c1"
    assert studio["language"] == "tr"
    assert studio["max_steps"] == 9
    assert callable(studio["progress_callback"])


def test_result_is_shown_after_recording(studio):
    at = AppTest.from_file(PAGE)
    at.run(timeout=60)
    _press_record(at)

    recording = at.session_state["a1_recording"]
    assert recording is not None
    assert recording.module == "c1"
    assert recording.step_count == 1
    assert at.exception == []


def test_silent_recording_reports_why_there_is_no_voice(studio):
    at = AppTest.from_file(PAGE)
    at.run(timeout=60)
    _press_record(at)

    warnings = " ".join(w.value for w in at.warning)
    assert "boto3" in warnings or "eslendirme" in warnings


def test_recording_cost_is_added_to_session_total(studio):
    at = AppTest.from_file(PAGE)
    at.run(timeout=60)
    before = at.session_state["total_cost_usd"]
    _press_record(at)
    assert at.session_state["total_cost_usd"] == pytest.approx(before + 0.0031)
