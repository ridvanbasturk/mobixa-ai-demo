"""A1 Faz 3 yerel MP4 üretimi için AWS'den bağımsız testler.

FFmpeg alt süreç çağrıları çoğu testte sahtelenir (mock); yalnızca FFmpeg bu
ortamda gerçekten kurulu ise çalışan tek bir gerçek entegrasyon testi
(tiny/1 saniyelik tek sahne) eklenmiştir.
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageFont

from schemas.a1_video_models import validate_video_settings
from services.a1_video_service import (
    FFMPEG_MISSING_MESSAGE,
    FFmpegProcessError,
    build_transition_filter_complex,
    calculate_expected_duration,
    check_overlay_content_warnings,
    compute_video_state_fingerprint,
    fit_image_to_canvas,
    generate_safe_filename,
    generate_video,
    get_subtitle_text,
    is_ffmpeg_available,
    is_near_duplicate,
    normalize_highlight_rect,
    validate_video_inputs,
    wrap_text,
)


def _png_bytes(w: int = 200, h: int = 100, color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _scene(scene_number, image_id, transition="cut", duration=4):
    return {
        "scene_number": scene_number,
        "image_id": image_id,
        "scene_title": f"Sahne {scene_number}",
        "duration_seconds": duration,
        "narration": f"Anlatım {scene_number}",
        "on_screen_text": f"Metin {scene_number}",
        "transition": transition,
        "zoom_enabled": True,
        "highlight_description": f"Vurgu {scene_number}",
        "requires_review": False,
    }


VALID_STORYBOARD = {
    "title": "Test",
    "target_audience": "Trainer",
    "tone": "Kurumsal",
    "scenes": [
        _scene(1, "screen_01", "cut", 4),
        _scene(2, "screen_02", "fade", 5),
    ],
    "total_duration_seconds": 9,
    "closing_text": "Kapanış",
}

DEFAULT_SETTINGS = validate_video_settings({"output_filename": "test.mp4"})


# --- validate_video_inputs ---------------------------------------------------


def test_missing_screenshot_for_image_id_fails():
    result = validate_video_inputs(VALID_STORYBOARD, {"screen_01": _png_bytes()})
    assert result["passed"] is False
    assert any("screen_02" in e for e in result["errors"])


def test_all_screenshots_present_passes():
    bytes_map = {"screen_01": _png_bytes(), "screen_02": _png_bytes()}
    result = validate_video_inputs(VALID_STORYBOARD, bytes_map)
    assert result["passed"] is True


def test_unreadable_image_fails():
    bytes_map = {"screen_01": b"not a real image", "screen_02": _png_bytes()}
    result = validate_video_inputs(VALID_STORYBOARD, bytes_map)
    assert result["passed"] is False
    assert any("screen_01" in e for e in result["errors"])


def test_missing_selected_storyboard_no_scenes_fails():
    result = validate_video_inputs({"scenes": []}, {})
    assert result["passed"] is False
    assert any("en az bir sahne" in e for e in result["errors"])


def test_invalid_scene_duration_fails():
    storyboard = {"scenes": [{"image_id": "screen_01", "duration_seconds": 0}]}
    result = validate_video_inputs(storyboard, {"screen_01": _png_bytes()})
    assert result["passed"] is False
    assert any("süresi geçersiz" in e for e in result["errors"])


# --- altyazı kaynağı seçimi -----------------------------------------------


def test_narration_is_default_subtitle_source():
    settings = validate_video_settings({"output_filename": "test.mp4"})
    assert settings.subtitle_source == "narration"


def test_get_subtitle_text_narration_source():
    scene = _scene(1, "screen_01")
    assert get_subtitle_text(scene, "narration") == scene["narration"]


def test_get_subtitle_text_on_screen_text_source():
    scene = _scene(1, "screen_01")
    assert get_subtitle_text(scene, "on_screen_text") == scene["on_screen_text"]


def test_get_subtitle_text_none_source_returns_empty():
    scene = _scene(1, "screen_01")
    assert get_subtitle_text(scene, "none") == ""


def test_invalid_subtitle_source_rejected():
    with pytest.raises(Exception):
        validate_video_settings({"output_filename": "test.mp4", "subtitle_source": "invalid"})


# --- tekrar (duplication) koruması -----------------------------------------


def test_is_near_duplicate_identical_short_texts():
    assert is_near_duplicate("Ana Panel", "Ana Panel") is True


def test_is_near_duplicate_case_and_punctuation_insensitive():
    assert is_near_duplicate("Ana Panel!", "ana panel") is True


def test_is_near_duplicate_false_for_narration_sharing_title_prefix():
    # Kısa bir başlığın, çok daha uzun bir anlatım cümlesinin doğal bir alt
    # dizesi olması tekrar SAYILMAZ (farklı ayrıntı düzeyi).
    title = "Ana Panel"
    narration = "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir."
    assert is_near_duplicate(narration, title) is False


def test_is_near_duplicate_false_for_unrelated_texts():
    assert is_near_duplicate("Ana Panel", "Yolculuklar") is False


def test_is_near_duplicate_empty_text_is_not_duplicate():
    assert is_near_duplicate("", "Ana Panel") is False
    assert is_near_duplicate("Ana Panel", "") is False


# --- alt yazı/başlık için içerik uyarıları -------------------------------------


def test_overlay_warning_when_narration_source_selected_but_narration_empty():
    storyboard = {"scenes": [dict(_scene(1, "screen_01"), narration="")]}
    settings = validate_video_settings({"output_filename": "test.mp4", "subtitle_source": "narration"})
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert any("screen_01" in w and "Anlatım" in w for w in warnings)


def test_overlay_warning_when_on_screen_text_source_selected_but_empty():
    storyboard = {"scenes": [dict(_scene(1, "screen_01"), on_screen_text="")]}
    settings = validate_video_settings({"output_filename": "test.mp4", "subtitle_source": "on_screen_text"})
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert any("screen_01" in w and "Ekran üstü metin" in w for w in warnings)


def test_no_overlay_warning_when_subtitle_source_none():
    storyboard = {"scenes": [dict(_scene(1, "screen_01"), narration="", on_screen_text="")]}
    settings = validate_video_settings({"output_filename": "test.mp4", "subtitle_source": "none"})
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert warnings == []


def test_no_overlay_warning_when_narration_present():
    storyboard = {"scenes": [_scene(1, "screen_01")]}
    settings = validate_video_settings({"output_filename": "test.mp4", "subtitle_source": "narration"})
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert warnings == []


def test_overlay_warning_when_scene_titles_enabled_but_title_empty():
    storyboard = {"scenes": [dict(_scene(1, "screen_01"), scene_title="")]}
    settings = validate_video_settings({"output_filename": "test.mp4", "scene_titles_enabled": True})
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert any("screen_01" in w and "başlıkları" in w for w in warnings)


def test_overlay_warning_when_title_will_be_auto_hidden_as_duplicate():
    storyboard = {
        "scenes": [
            dict(_scene(1, "screen_01"), scene_title="Ana Panel", on_screen_text="Ana Panel")
        ]
    }
    settings = validate_video_settings(
        {"output_filename": "test.mp4", "subtitle_source": "on_screen_text", "scene_titles_enabled": True}
    )
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert any("otomatik olarak gizlenecek" in w for w in warnings)


def test_scene_title_toggle_independent_of_subtitle_source():
    # subtitle_source "none" olsa bile scene_titles_enabled bağımsız çalışmalı.
    storyboard = {"scenes": [_scene(1, "screen_01")]}
    settings = validate_video_settings(
        {"output_filename": "test.mp4", "subtitle_source": "none", "scene_titles_enabled": False}
    )
    warnings = check_overlay_content_warnings(storyboard, settings)
    assert warnings == []


# --- fit_image_to_canvas (en-boy oranı korunur) ------------------------------


def test_fit_image_letterboxes_wide_image():
    img = Image.new("RGB", (400, 100), "red")
    canvas = fit_image_to_canvas(img, (1280, 720))
    assert canvas.size == (1280, 720)
    assert canvas.getpixel((0, 0)) == (24, 24, 26)


def test_fit_image_pillarboxes_tall_image():
    img = Image.new("RGB", (100, 400), "blue")
    canvas = fit_image_to_canvas(img, (1280, 720))
    assert canvas.size == (1280, 720)
    assert canvas.getpixel((0, 0)) == (24, 24, 26)


def test_fit_image_matching_ratio_fills_frame():
    img = Image.new("RGB", (1280, 720), (0, 128, 0))
    canvas = fit_image_to_canvas(img, (1280, 720))
    assert canvas.size == (1280, 720)
    assert canvas.getpixel((0, 0)) == (0, 128, 0)


# --- güvenli dosya adı --------------------------------------------------------


def test_safe_filename_from_title():
    assert generate_safe_filename("Yeni Öğrenme Yolculuğu") == "yeni_ogrenme_yolculugu.mp4"


def test_safe_filename_prevents_path_traversal():
    name = generate_safe_filename("../../../etc/passwd")
    assert "/" not in name
    assert ".." not in name
    assert "\\" not in name


def test_safe_filename_empty_title_uses_fallback():
    assert generate_safe_filename("") == "a1_tutorial_video.mp4"


# --- altyazı satır bölme -----------------------------------------------------


def test_wrap_text_short_text_single_line():
    font = ImageFont.load_default(size=24)
    assert wrap_text("Kısa metin", font, 1000) == ["Kısa metin"]


def test_wrap_text_long_text_wraps_multiple_lines():
    font = ImageFont.load_default(size=24)
    long_text = "Bu metin oldukça uzun olmalı ve satırlara bölünmesi gerekir çünkü genişlik sınırlıdır"
    lines = wrap_text(long_text, font, 200)
    assert len(lines) > 1


def test_wrap_text_empty_text_returns_empty_list():
    font = ImageFont.load_default(size=24)
    assert wrap_text("", font, 500) == []
    assert wrap_text("   ", font, 500) == []


def test_wrap_text_long_turkish_narration_wraps_multiline_and_preserves_characters():
    font = ImageFont.load_default(size=24)
    narration = (
        "Ana panelden sol menüdeki Öğrenme Yolculukları bölümüne gidilir ve "
        "buradan yeni bir yolculuk oluşturulabilir çünkü ığüşöçİ karakterleri de içerir."
    )
    lines = wrap_text(narration, font, 220)
    assert len(lines) > 1
    joined = " ".join(lines)
    for ch in "ığüşöçİ":
        assert ch in joined
    for line in lines:
        assert font.getlength(line) <= 220 or " " not in line


# --- Türkçe karakter render fallback -----------------------------------------


def test_turkish_characters_measurable_with_default_font_fallback():
    font = ImageFont.load_default(size=24)
    assert font.getlength("Türkçe ığüşöçİ karakterleri") > 0


# --- vurgu (highlight) dikdörtgeni --------------------------------------------


def test_normalize_highlight_rect_valid():
    rect = normalize_highlight_rect({"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1})
    assert rect is not None
    assert rect.x == 0.1
    assert rect.width == 0.3


def test_normalize_highlight_rect_none_when_absent():
    assert normalize_highlight_rect(None) is None
    assert normalize_highlight_rect({}) is None


def test_normalize_highlight_rect_clamps_out_of_bounds():
    rect = normalize_highlight_rect({"x": 0.9, "y": 0.1, "width": 0.5, "height": 0.2})
    assert rect is not None
    assert rect.x + rect.width <= 1.0 + 1e-9


def test_normalize_highlight_rect_rejects_non_positive_size():
    assert normalize_highlight_rect({"x": 0.1, "y": 0.1, "width": 0, "height": 0.2}) is None
    assert normalize_highlight_rect({"x": 0.1, "y": 0.1, "width": -0.1, "height": 0.2}) is None


# --- beklenen süre hesaplama --------------------------------------------------


def test_calculate_expected_duration_sums_scene_durations():
    assert calculate_expected_duration(VALID_STORYBOARD) == 9.0


def test_calculate_expected_duration_empty_scenes_is_zero():
    assert calculate_expected_duration({"scenes": []}) == 0.0


# --- eskime (stale) tespiti: parmak izi ---------------------------------------


def test_fingerprint_changes_when_storyboard_changes():
    fp1 = compute_video_state_fingerprint(VALID_STORYBOARD, DEFAULT_SETTINGS)
    changed = {**VALID_STORYBOARD, "closing_text": "Farklı kapanış"}
    fp2 = compute_video_state_fingerprint(changed, DEFAULT_SETTINGS)
    assert fp1 != fp2


def test_fingerprint_changes_when_settings_change():
    fp1 = compute_video_state_fingerprint(VALID_STORYBOARD, DEFAULT_SETTINGS)
    other_settings = validate_video_settings({"output_filename": "test.mp4", "resolution": "1920x1080"})
    fp2 = compute_video_state_fingerprint(VALID_STORYBOARD, other_settings)
    assert fp1 != fp2


def test_fingerprint_stable_for_identical_input():
    fp1 = compute_video_state_fingerprint(VALID_STORYBOARD, DEFAULT_SETTINGS)
    fp2 = compute_video_state_fingerprint(dict(VALID_STORYBOARD), DEFAULT_SETTINGS)
    assert fp1 == fp2


# --- geçiş (transition) filter_complex üretimi ---------------------------------


def test_filter_complex_all_cuts_uses_no_xfade():
    fc, _ = build_transition_filter_complex([5.0, 6.0], ["cut", "cut"])
    assert "xfade" not in fc
    assert "concat" in fc


def test_filter_complex_with_fade_uses_xfade():
    fc, _ = build_transition_filter_complex([5.0, 6.0], ["cut", "fade"])
    assert "xfade" in fc
    assert "offset=4.600" in fc


def test_filter_complex_normalizes_timebase_for_every_raw_input():
    # "First input link main timebase ... do not match ..." xfade hatasını
    # önlemek için her ham girdi ([i:v]) settb=AVTB ile normalize edilmeli.
    fc, _ = build_transition_filter_complex([4.0, 5.0, 6.0], ["cut", "cut", "fade"])
    assert fc.count("settb=AVTB") == 3
    assert "[0:v]settb=AVTB[b0]" in fc
    assert "[1:v]settb=AVTB[b1]" in fc
    assert "[2:v]settb=AVTB[b2]" in fc
    # Zincirleme düğümler artık normalize edilmiş [bN] etiketlerini kullanmalı,
    # ham [N:v] etiketlerini doğrudan değil.
    assert "[b0][b1]concat" in fc
    assert "[v1][b2]xfade" in fc


def test_filter_complex_chained_fades_offsets_still_correct():
    fc, final_label = build_transition_filter_complex([4.0, 6.0, 5.0], ["cut", "fade", "fade"])
    assert "offset=3.600" in fc  # 4.0 - 0.4
    assert "offset=9.200" in fc  # (4.0 + 6.0 - 0.4) - 0.4
    assert final_label == "v2"


# --- FFmpeg eksik davranışı ----------------------------------------------------


def test_generate_video_returns_clear_error_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: False)
    screen_bytes = {"screen_01": _png_bytes(), "screen_02": _png_bytes()}
    result = generate_video(VALID_STORYBOARD, screen_bytes, DEFAULT_SETTINGS)
    assert result.success is False
    assert result.ffmpeg_available is False
    assert result.error == FFMPEG_MISSING_MESSAGE


def test_generate_video_fails_cleanly_when_inputs_invalid(monkeypatch):
    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    result = generate_video({"scenes": []}, {}, DEFAULT_SETTINGS)
    assert result.success is False
    assert "en az bir sahne" in result.error


# --- geçici dizin temizliği + sahte FFmpeg ile üretim ---------------------------


def _fake_run_ffmpeg_writes_output(args, timeout):
    output_path = Path(args[-1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-mp4-bytes")


def test_one_scene_storyboard_is_valid_and_not_treated_as_error(monkeypatch, tmp_path):
    """Tek ekran görüntüsü kasıtlı olarak seçildiğinde tek sahneli video geçerli kalmalı."""
    fake_tmp_dir = tmp_path / "a1_video_fake_one_scene"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", _fake_run_ffmpeg_writes_output)
    monkeypatch.setattr("services.a1_video_service._probe_duration_seconds", lambda path, timeout=15: 4.0)

    one_scene_storyboard = {
        "title": "Tek Sahne",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [_scene(1, "screen_01")],
        "total_duration_seconds": 4,
        "closing_text": "Kapanış",
    }
    input_validation = validate_video_inputs(one_scene_storyboard, {"screen_01": _png_bytes()})
    assert input_validation["passed"] is True
    assert input_validation["errors"] == []

    result = generate_video(one_scene_storyboard, {"screen_01": _png_bytes()}, DEFAULT_SETTINGS)
    assert result.success is True
    assert result.scene_count == 1


# --- Faz 4C: tekrarlanan image_id (alt sahne genişletmesi) render desteği ----


def test_repeated_image_id_produces_unique_segment_files(monkeypatch, tmp_path):
    fake_tmp_dir = tmp_path / "a1_video_fake_repeated"
    fake_tmp_dir.mkdir()
    segment_output_paths = []

    def _tracking_run_ffmpeg(args, timeout):
        output_path = Path(args[-1])
        segment_output_paths.append(output_path.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-bytes")

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", _tracking_run_ffmpeg)
    monkeypatch.setattr("services.a1_video_service._probe_duration_seconds", lambda path, timeout=15: 8.0)

    repeated_storyboard = {
        "title": "Tekrarlanan Ekran",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [
            dict(_scene(1, "screen_03"), scene_id="screen_03_step_01"),
            dict(_scene(2, "screen_03"), scene_id="screen_03_step_02"),
        ],
        "total_duration_seconds": 8,
        "closing_text": "Kapanış",
    }
    screen_bytes = {"screen_03": _png_bytes()}

    result = generate_video(repeated_storyboard, screen_bytes, DEFAULT_SETTINGS)

    assert result.success is True
    assert result.scene_count == 2
    # Aynı image_id'ye rağmen iki farklı segment dosyası üretilmiş olmalı
    # (scene_id'ye dayalı isimlendirme sayesinde birbirinin üzerine yazılmaz).
    mp4_segments = [p for p in segment_output_paths if p.endswith(".mp4") and p != "final_output.mp4"]
    assert len(mp4_segments) == 2
    assert len(set(mp4_segments)) == 2
    assert "screen_03_step_01" in mp4_segments[0]
    assert "screen_03_step_02" in mp4_segments[1]


def test_repeated_image_id_scenes_may_use_different_highlight_settings(monkeypatch, tmp_path):
    fake_tmp_dir = tmp_path / "a1_video_fake_repeated_highlight"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", _fake_run_ffmpeg_writes_output)
    monkeypatch.setattr("services.a1_video_service._probe_duration_seconds", lambda path, timeout=15: 10.0)

    scene1 = dict(_scene(1, "screen_03"), scene_id="screen_03_step_01")
    scene2 = dict(_scene(2, "screen_03"), scene_id="screen_03_step_02")
    scene2["highlight_rect"] = {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}
    scene2["cursor_enabled"] = True
    scene2["click_effect_enabled"] = True

    repeated_storyboard = {
        "title": "Tekrarlanan Ekran Farklı Vurgu",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [scene1, scene2],
        "total_duration_seconds": 20,
        "closing_text": "Kapanış",
    }
    result = generate_video(repeated_storyboard, {"screen_03": _png_bytes()}, DEFAULT_SETTINGS)

    assert result.success is True
    assert result.scene_count == 2


def test_single_scene_backward_compatible_without_scene_id(monkeypatch, tmp_path):
    """Eski (Faz 4C öncesi, scene_id İÇERMEYEN) tek sahneli storyboard'lar render'da hâlâ çalışmalı."""
    fake_tmp_dir = tmp_path / "a1_video_fake_legacy"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", _fake_run_ffmpeg_writes_output)
    monkeypatch.setattr("services.a1_video_service._probe_duration_seconds", lambda path, timeout=15: 4.0)

    legacy_storyboard = {
        "title": "Eski Storyboard",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [_scene(1, "screen_01")],  # scene_id yok
        "total_duration_seconds": 4,
        "closing_text": "Kapanış",
    }
    result = generate_video(legacy_storyboard, {"screen_01": _png_bytes()}, DEFAULT_SETTINGS)
    assert result.success is True
    assert result.scene_count == 1


def test_temp_directory_cleaned_up_on_success(monkeypatch, tmp_path):
    fake_tmp_dir = tmp_path / "a1_video_fake_success"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", _fake_run_ffmpeg_writes_output)
    monkeypatch.setattr("services.a1_video_service._probe_duration_seconds", lambda path, timeout=15: 9.0)

    screen_bytes = {"screen_01": _png_bytes(), "screen_02": _png_bytes()}
    result = generate_video(VALID_STORYBOARD, screen_bytes, DEFAULT_SETTINGS)

    assert result.success is True
    assert result.temp_files_cleaned is True
    assert not fake_tmp_dir.exists()


def test_temp_directory_cleaned_up_on_failure(monkeypatch, tmp_path):
    fake_tmp_dir = tmp_path / "a1_video_fake_failure"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))

    def failing_run_ffmpeg(args, timeout):
        raise FFmpegProcessError("simulated encode failure")

    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", failing_run_ffmpeg)

    screen_bytes = {"screen_01": _png_bytes(), "screen_02": _png_bytes()}
    result = generate_video(VALID_STORYBOARD, screen_bytes, DEFAULT_SETTINGS)

    assert result.success is False
    assert "FFmpeg işlemi başarısız oldu" in result.error
    assert result.temp_files_cleaned is True
    assert not fake_tmp_dir.exists()


def test_temp_files_cleaned_flag_false_when_rmtree_fails(monkeypatch, tmp_path):
    fake_tmp_dir = tmp_path / "a1_video_fake_rmtree_fail"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", _fake_run_ffmpeg_writes_output)
    monkeypatch.setattr("services.a1_video_service._probe_duration_seconds", lambda path, timeout=15: 9.0)

    def failing_rmtree(*args, **kwargs):
        raise OSError("simulated disk error")

    monkeypatch.setattr("services.a1_video_service.shutil.rmtree", failing_rmtree)

    screen_bytes = {"screen_01": _png_bytes(), "screen_02": _png_bytes()}
    result = generate_video(VALID_STORYBOARD, screen_bytes, DEFAULT_SETTINGS)

    assert result.success is True
    assert result.temp_files_cleaned is False


def test_encoding_timeout_handled_cleanly(monkeypatch, tmp_path):
    fake_tmp_dir = tmp_path / "a1_video_fake_timeout"
    fake_tmp_dir.mkdir()

    monkeypatch.setattr("services.a1_video_service.is_ffmpeg_available", lambda: True)
    monkeypatch.setattr("services.a1_video_service.tempfile.mkdtemp", lambda prefix="": str(fake_tmp_dir))
    monkeypatch.setenv("A1_VIDEO_ENCODING_TIMEOUT_SECONDS", "5")

    def timeout_run_ffmpeg(args, timeout):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)

    monkeypatch.setattr("services.a1_video_service._run_ffmpeg", timeout_run_ffmpeg)

    screen_bytes = {"screen_01": _png_bytes(), "screen_02": _png_bytes()}
    result = generate_video(VALID_STORYBOARD, screen_bytes, DEFAULT_SETTINGS)

    assert result.success is False
    assert "5 saniye" in result.error
    assert result.temp_files_cleaned is True
    assert not fake_tmp_dir.exists()


# --- gerçek FFmpeg entegrasyon testi (yalnızca FFmpeg mevcutsa) ----------------


@pytest.mark.skipif(not is_ffmpeg_available(), reason="FFmpeg bu ortamda mevcut değil")
def test_real_ffmpeg_generates_tiny_one_scene_video():
    tiny_storyboard = {
        "title": "Entegrasyon Testi",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [
            {
                "scene_number": 1,
                "image_id": "screen_01",
                "scene_title": "Test",
                "duration_seconds": 1,
                "narration": "Test.",
                "on_screen_text": "Test Türkçe ığüşöç",
                "transition": "cut",
                "zoom_enabled": True,
                "highlight_description": "H",
                "requires_review": False,
            }
        ],
        "total_duration_seconds": 1,
        "closing_text": "Bitiş.",
    }
    settings = validate_video_settings({"output_filename": "integration_test.mp4"})
    screen_bytes = {"screen_01": _png_bytes(64, 64)}

    result = generate_video(tiny_storyboard, screen_bytes, settings)

    assert result.success is True, result.error
    assert result.video_bytes is not None
    assert len(result.video_bytes) > 0
    assert result.temp_files_cleaned is True
    assert result.actual_duration_seconds is not None
    assert abs(result.actual_duration_seconds - 1.0) < 1.5


@pytest.mark.skipif(not is_ffmpeg_available(), reason="FFmpeg bu ortamda mevcut değil")
def test_real_ffmpeg_multi_scene_repeated_image_integration():
    """Faz 4C: aynı ekran görüntüsünün iki farklı alt sahnede (farklı vurgu
    koordinatlarıyla) kullanıldığı gerçek bir FFmpeg render'ı doğrular."""
    tiny_storyboard = {
        "title": "Tekrarlanan Ekran Entegrasyon Testi",
        "target_audience": "Trainer",
        "tone": "Kurumsal",
        "scenes": [
            {
                "scene_id": "screen_01_step_01",
                "scene_number": 1,
                "image_id": "screen_01",
                "scene_title": "Adım 1",
                "duration_seconds": 1,
                "narration": "Birinci alt sahne.",
                "on_screen_text": "Adım 1",
                "transition": "cut",
                "zoom_enabled": True,
                "highlight_description": "H1",
                "requires_review": True,
                "highlight_rect": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
            },
            {
                "scene_id": "screen_01_step_02",
                "scene_number": 2,
                "image_id": "screen_01",
                "scene_title": "Adım 2",
                "duration_seconds": 1,
                "narration": "İkinci alt sahne.",
                "on_screen_text": "Adım 2",
                "transition": "cut",
                "zoom_enabled": True,
                "highlight_description": "H2",
                "requires_review": True,
                "highlight_rect": {"x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1},
            },
        ],
        "total_duration_seconds": 2,
        "closing_text": "Bitiş.",
    }
    settings = validate_video_settings({"output_filename": "integration_repeated.mp4"})
    screen_bytes = {"screen_01": _png_bytes(64, 64)}

    result = generate_video(tiny_storyboard, screen_bytes, settings)

    assert result.success is True, result.error
    assert result.scene_count == 2
    assert result.video_bytes is not None and len(result.video_bytes) > 0
    assert result.actual_duration_seconds is not None
    assert abs(result.actual_duration_seconds - 2.0) < 1.5
