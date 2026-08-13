"""Video/altyazı post-prodüksiyon testleri — FFmpeg GERÇEKTEN çalıştırılmaz.

Komutların doğru kurulduğu ve SRT'nin doğru üretildiği test edilir.
"""
from __future__ import annotations

from pathlib import Path

from schemas.tour_models import TourStep
from services.tour_video_service import (
    FFMPEG_MISSING_MESSAGE,
    _format_timestamp,
    build_audio_timeline_command,
    build_render_command,
    build_srt,
    render_final_video,
    write_srt,
)


def _step(index=1, start=0.0, duration=3.0, narration="Anlatım.", audio=None):
    return TourStep(
        index=index,
        action="click",
        narration=narration,
        start_seconds=start,
        duration_seconds=duration,
        audio_path=audio,
    )


def test_timestamp_formatting():
    assert _format_timestamp(0) == "00:00:00,000"
    assert _format_timestamp(1.25) == "00:00:01,250"
    assert _format_timestamp(65.5) == "00:01:05,500"
    assert _format_timestamp(3661.001) == "01:01:01,001"


def test_negative_timestamp_is_clamped_to_zero():
    assert _format_timestamp(-5) == "00:00:00,000"


def test_srt_contains_every_step_in_order():
    steps = [
        _step(1, 0.0, 2.0, "Birinci adım."),
        _step(2, 2.0, 3.0, "İkinci adım."),
    ]
    srt = build_srt(steps)
    assert "1\n00:00:00,000 --> 00:00:02,000\nBirinci adım." in srt
    assert "2\n00:00:02,000 --> 00:00:05,000\nİkinci adım." in srt


def test_srt_enforces_minimum_visible_duration():
    # Sıfır süreli bir adımın altyazısı görünmeden kaybolmamalı.
    srt = build_srt([_step(1, 0.0, 0.0, "Çok kısa.")])
    assert "--> 00:00:00,800" in srt


def test_srt_written_as_utf8_preserves_turkish_characters(tmp_path):
    path = write_srt([_step(1, 0.0, 2.0, "Şifre değiştirme ığüöç")], tmp_path / "a.srt")
    assert "Şifre değiştirme ığüöç" in path.read_text(encoding="utf-8")


def test_render_command_without_audio_disables_sound():
    command = build_render_command(Path("in.webm"), Path("out.mp4"))
    assert "-an" in command
    assert "libx264" in command
    assert command[-1] == "out.mp4"
    assert "+faststart" in command


def test_render_command_with_audio_maps_both_streams():
    command = build_render_command(Path("in.webm"), Path("out.mp4"), audio_path=Path("narration.mp3"))
    assert "-an" not in command
    assert "0:v:0" in command
    assert "1:a:0" in command
    assert "-shortest" in command


def test_render_command_burns_subtitles_when_given():
    command = build_render_command(Path("in.webm"), Path("out.mp4"), subtitle_path=Path("a.srt"))
    filter_arg = command[command.index("-vf") + 1]
    assert "subtitles=" in filter_arg
    assert "force_style=" in filter_arg


def test_subtitle_path_escaping_handles_windows_paths():
    command = build_render_command(
        Path("in.webm"), Path("out.mp4"), subtitle_path=Path(r"C:\Users\demo\a.srt")
    )
    filter_arg = command[command.index("-vf") + 1]
    # Ters bölü ileri bölüye çevrilir ve sürücü harfindeki iki nokta kaçışlanır;
    # aksi halde FFmpeg filtre dizesi ayrıştırılamaz.
    assert "\\" not in filter_arg.split("force_style")[0].replace("\\:", "")
    assert r"C\:/Users/demo/a.srt" in filter_arg


def test_audio_timeline_delays_each_segment_to_its_own_start():
    segments = [(Path("a.mp3"), 0.0), (Path("b.mp3"), 4.5)]
    command = build_audio_timeline_command(segments, Path("out.mp3"), total_seconds=10.0)
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "adelay=0|0" in filter_complex
    assert "adelay=4500|4500" in filter_complex
    assert "amix=inputs=2" in filter_complex
    assert "10.000" in command[command.index("-t") + 1]


def test_render_reports_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr("services.tour_video_service.is_ffmpeg_available", lambda: False)
    result = render_final_video(Path("in.webm"), [], Path("out.mp4"))
    assert result["success"] is False
    assert result["error"] == FFMPEG_MISSING_MESSAGE


def test_render_reports_missing_raw_recording(monkeypatch, tmp_path):
    monkeypatch.setattr("services.tour_video_service.is_ffmpeg_available", lambda: True)
    result = render_final_video(tmp_path / "yok.webm", [_step()], tmp_path / "out.mp4")
    assert result["success"] is False
    assert "bulunamadı" in result["error"]
