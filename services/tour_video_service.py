"""Kaydedilen ham videoyu yayınlanabilir bir MP4'e çevirir.

Girdi: Playwright'ın ürettiği .webm + adım zaman çizelgesi (+ varsa Polly
ses dosyaları). Çıktı: altyazısı gömülü, sesi hizalanmış .mp4

FFmpeg sistemde kurulu olmalıdır (PATH üzerinden çağrılır). Kurulu değilse
fonksiyonlar temiz bir hata döner; çağıran taraf ham .webm'i yine de sunabilir.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

from schemas.tour_models import TourStep

FFMPEG_MISSING_MESSAGE = (
    "FFmpeg bulunamadı. Videoyu MP4'e çevirmek ve altyazı gömmek için FFmpeg "
    "kurulu ve PATH üzerinde erişilebilir olmalıdır."
)

# Altyazı görünümü (libass). Türkçe karakterler için özel bir ayar gerekmez;
# .srt dosyası UTF-8 yazılır ve libass doğru işler.
SUBTITLE_STYLE = (
    "FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,"
    "BorderStyle=3,Outline=1,Shadow=0,MarginV=28,Alignment=2"
)


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _format_timestamp(seconds: float) -> str:
    """Saniyeyi SRT zaman damgasına çevirir (00:00:01,250)."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(steps: Sequence[TourStep]) -> str:
    """Adım zaman çizelgesinden SRT altyazı metni üretir."""
    blocks: List[str] = []
    for order, step in enumerate(steps, start=1):
        start = _format_timestamp(step.start_seconds)
        end = _format_timestamp(max(step.end_seconds, step.start_seconds + 0.8))
        blocks.append(f"{order}\n{start} --> {end}\n{step.narration}\n")
    return "\n".join(blocks)


def write_srt(steps: Sequence[TourStep], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_srt(steps), encoding="utf-8")
    return path


def _escape_subtitle_path(path: Path) -> str:
    """FFmpeg filtre dizesi için yol kaçışlaması (Windows dahil).

    `subtitles=` filtresi içinde ters bölü ve iki nokta özel karakterdir;
    Windows yollarında ikisi de bulunur.
    """
    text = str(path).replace("\\", "/")
    return text.replace(":", r"\:")


def build_render_command(
    video_path: Path,
    output_path: Path,
    subtitle_path: Optional[Path] = None,
    audio_path: Optional[Path] = None,
) -> List[str]:
    """Nihai MP4'ü üreten FFmpeg komutunu kurar (test edilebilir olsun diye ayrı)."""
    command: List[str] = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path)]

    if audio_path is not None:
        command += ["-i", str(audio_path)]

    if subtitle_path is not None:
        command += ["-vf", f"subtitles='{_escape_subtitle_path(subtitle_path)}':force_style='{SUBTITLE_STYLE}'"]

    command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]

    if audio_path is not None:
        command += ["-c:a", "aac", "-b:a", "128k", "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    else:
        command += ["-an"]

    command += ["-movflags", "+faststart", str(output_path)]
    return command


def build_audio_timeline_command(
    segments: Sequence[tuple],
    output_path: Path,
    total_seconds: float,
) -> List[str]:
    """Adım seslerini kendi başlangıç saniyelerine yerleştiren komutu kurar.

    `segments`: (audio_path, start_seconds) çiftleri. Her ses `adelay` ile
    kendi zamanına kaydırılır, hepsi `amix` ile tek kanalda birleştirilir;
    böylece ses altyazıyla senkron kalır.
    """
    command: List[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for audio_path, _ in segments:
        command += ["-i", str(audio_path)]

    filters = []
    for index, (_, start_seconds) in enumerate(segments):
        delay_ms = max(0, int(round(start_seconds * 1000)))
        filters.append(f"[{index}:a]adelay={delay_ms}|{delay_ms}[a{index}]")

    mix_inputs = "".join(f"[a{index}]" for index in range(len(segments)))
    filters.append(f"{mix_inputs}amix=inputs={len(segments)}:normalize=0:dropout_transition=0[out]")

    command += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-t",
        f"{max(total_seconds, 0.1):.3f}",
        "-c:a",
        "mp3",
        str(output_path),
    ]
    return command


def _run(command: Sequence[str], timeout: int = 600) -> tuple:
    try:
        result = subprocess.run(list(command), capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, FFMPEG_MISSING_MESSAGE
    except subprocess.SubprocessError as exc:
        return False, f"FFmpeg çalıştırılamadı: {exc}"
    if result.returncode != 0:
        return False, (result.stderr or "").strip()[:600] or "FFmpeg bilinmeyen bir hata verdi."
    return True, ""


def build_audio_track(steps: Sequence[TourStep], total_seconds: float, work_dir: Path) -> Optional[Path]:
    """Adım seslerini tek bir zaman-hizalı ses kanalına birleştirir.

    Hiç ses yoksa None döner (video sessiz kalır).
    """
    segments = [
        (Path(step.audio_path), step.start_seconds)
        for step in steps
        if step.audio_path and Path(step.audio_path).exists()
    ]
    if not segments:
        return None

    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / "narration.mp3"
    success, _ = _run(build_audio_timeline_command(segments, output_path, total_seconds))
    return output_path if success and output_path.exists() else None


def render_final_video(
    raw_video_path: Path,
    steps: Sequence[TourStep],
    output_path: Path,
    subtitle_path: Optional[Path] = None,
    total_seconds: Optional[float] = None,
) -> dict:
    """Ham kaydı altyazılı/sesli nihai MP4'e çevirir.

    Döner: {"success": bool, "output_path": Path|None, "error": str,
            "voiced": bool}
    """
    if not is_ffmpeg_available():
        return {"success": False, "output_path": None, "error": FFMPEG_MISSING_MESSAGE, "voiced": False}
    if not raw_video_path.exists():
        return {
            "success": False,
            "output_path": None,
            "error": f"Ham kayıt bulunamadı: {raw_video_path}",
            "voiced": False,
        }

    duration = total_seconds or (steps[-1].end_seconds if steps else 0.0)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tour_render_") as tmp:
        work_dir = Path(tmp)
        audio_path = build_audio_track(steps, duration, work_dir)
        success, error = _run(
            build_render_command(
                raw_video_path,
                output_path,
                subtitle_path=subtitle_path,
                audio_path=audio_path,
            )
        )

    if not success:
        return {"success": False, "output_path": None, "error": error, "voiced": False}
    return {
        "success": True,
        "output_path": output_path,
        "error": "",
        "voiced": any(step.audio_path for step in steps),
    }
