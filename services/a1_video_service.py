"""A1 için yerel, deterministik sessiz MP4 üretimi (Pillow + FFmpeg).

Bu modül Streamlit'ten bağımsızdır. Herhangi bir üretici (generative) video
modeli KULLANMAZ; yalnızca seçili storyboard'un sahnelerinden ve oturumda
tutulan gerçek ekran görüntüsü baytlarından, Pillow ile kare kompozisyonu ve
FFmpeg alt süreciyle kodlama yaparak deterministik bir video üretir.

Boru hattı:
1) Girdi doğrulaması (storyboard <-> ekran görüntüsü eşleşmesi).
2) Her sahne için sabit sayıda (NUM_ZOOM_KEYFRAMES) anahtar kare Pillow ile
   çizilir (yakınlaştırma, alt yazı, sahne başlığı, vurgu dikdörtgeni).
3) Her sahnenin kareleri FFmpeg ile sessiz, kısa bir MP4 segmentine kodlanır.
4) Segmentler, sahnelerin transition değerine göre (fade: xfade filtresi,
   cut: concat demuxer) tek bir MP4'te birleştirilir.
5) Tüm ara dosyalar (kareler, segmentler) geçici bir dizinde tutulur ve
   işlem başarılı ya da başarısız olsun fark etmeksizin silinir.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import string
import subprocess
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from schemas.a1_video_models import SUBTITLE_SOURCE_OPTIONS, HighlightRect, VideoSettings

# --- Sabitler -----------------------------------------------------------

NUM_ZOOM_KEYFRAMES = 12
ZOOM_MAX_SCALE = 1.06
FADE_DURATION_SECONDS = 0.4
BACKGROUND_COLOR = (24, 24, 26)
SAFE_MARGIN_RATIO = 0.06
DEFAULT_ENCODING_TIMEOUT_SECONDS = 180

# Türkçe karakterleri destekleyen, Windows'ta yaygın olarak bulunan
# fontlar. Herhangi bir font dosyası uygulamayla birlikte paketlenmez veya
# dışa açılmaz; yalnızca sistemde zaten mevcutsa kullanılır.
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

FFMPEG_MISSING_MESSAGE = (
    "FFmpeg bulunamadı. Video üretimi için FFmpeg'in sistem PATH'ine ekli "
    "olması gerekir. Kurulum sonrası uygulamayı yeniden başlatın. A1'in "
    "diğer bölümleri (proje hazırlığı ve storyboard üretimi) bu olmadan da "
    "çalışmaya devam eder."
)


class FFmpegProcessError(RuntimeError):
    """FFmpeg alt süreci sıfırdan farklı bir çıkış koduyla döndüğünde fırlatılır."""


# --- Ortam / yetenek kontrolü --------------------------------------------


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def is_ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def get_encoding_timeout_seconds() -> int:
    """A1_VIDEO_ENCODING_TIMEOUT_SECONDS ortam değişkeninden zaman aşımını okur (sır içermez)."""
    return int(os.environ.get("A1_VIDEO_ENCODING_TIMEOUT_SECONDS", DEFAULT_ENCODING_TIMEOUT_SECONDS))


# --- Güvenli dosya adı ----------------------------------------------------


def generate_safe_filename(title: str, extension: str = "mp4") -> str:
    """Proje başlığından güvenli (yol geçişi/path traversal içermeyen) bir dosya adı üretir."""
    normalized = unicodedata.normalize("NFKD", title or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    if not slug:
        slug = "a1_tutorial_video"
    return f"{slug}.{extension}"


# --- Vurgu (highlight) dikdörtgeni ----------------------------------------


def normalize_highlight_rect(data: Optional[Dict]) -> Optional[HighlightRect]:
    """Ham (dict) vurgu koordinatını doğrular/kırpar (clamp).

    Koordinat yoksa veya onarılamayacak kadar geçersizse (ör. genişlik/
    yükseklik <= 0) None döner — hiçbir koordinat uydurulmaz.
    """
    if not data:
        return None
    try:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        width = float(data.get("width", 0))
        height = float(data.get("height", 0))
    except (TypeError, ValueError):
        return None

    if width <= 0 or height <= 0:
        return None

    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)
    width = min(width, 1.0 - x)
    height = min(height, 1.0 - y)
    if width <= 0 or height <= 0:
        return None

    try:
        return HighlightRect(x=x, y=y, width=width, height=height)
    except Exception:  # noqa: BLE001 - herhangi bir kalıntı doğrulama hatası güvenle None'a düşer
        return None


# --- Kare kompozisyonu (Pillow) -------------------------------------------


def fit_image_to_canvas(
    img: Image.Image, target_size: Tuple[int, int], background_color: Tuple[int, int, int] = BACKGROUND_COLOR
) -> Image.Image:
    """Görseli en-boy oranını koruyarak hedef çözünürlüğe sığdırır.

    Oran uyuşmazsa nötr koyu bir arka planla doldurulur (letterbox/pillarbox).
    """
    target_w, target_h = target_size
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", target_size, background_color)
    offset = ((target_w - new_w) // 2, (target_h - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas


def apply_zoom(
    canvas: Image.Image, progress: float, focus: Tuple[float, float] = (0.5, 0.5)
) -> Image.Image:
    """canvas'ı progress (0..1) oranında 1.0 -> ZOOM_MAX_SCALE arasında yakınlaştırır.

    focus, 0-1 arası (x, y) normalize koordinatıdır; yakınlaştırma bu noktaya
    odaklanır (varsayılan: görsel merkezi).
    """
    target_w, target_h = canvas.size
    progress = min(max(progress, 0.0), 1.0)
    if progress <= 0:
        return canvas.copy()

    scale = 1.0 + (ZOOM_MAX_SCALE - 1.0) * progress
    big_w, big_h = round(target_w * scale), round(target_h * scale)
    enlarged = canvas.resize((big_w, big_h), Image.LANCZOS)

    focus_x, focus_y = focus
    center_x = big_w * focus_x
    center_y = big_h * focus_y
    left = min(max(center_x - target_w / 2, 0), big_w - target_w)
    top = min(max(center_y - target_h / 2, 0), big_h - target_h)
    box = (round(left), round(top), round(left) + target_w, round(top) + target_h)
    return enlarged.crop(box)


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    """Metni, verilen fontla max_width piksel genişliği aşmayacak satırlara böler."""
    words = (text or "").split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _load_font(size: int) -> ImageFont.ImageFont:
    """Türkçe karakterleri destekleyen bir sistem fontu yükler; yoksa güvenli bir yedeğe düşer."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:  # noqa: BLE001
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Eski Pillow sürümlerinde load_default size parametresi almaz.
        return ImageFont.load_default()


def get_subtitle_text(scene: Dict, subtitle_source: str) -> str:
    """subtitle_source ayarına göre sahneden gösterilecek altyazı metnini seçer.

    - "narration": tam anlatım cümlesi (seslendirme metni, varsayılan).
    - "on_screen_text": kısa ekran üstü çağrı metni.
    - "none" (veya bilinmeyen bir değer): altyazı gösterilmez.
    """
    if subtitle_source == "narration":
        return (scene.get("narration") or "").strip()
    if subtitle_source == "on_screen_text":
        return (scene.get("on_screen_text") or "").strip()
    return ""


def _normalize_for_comparison(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = normalized.replace("İ", "i").replace("I", "ı").casefold()
    return "".join(ch for ch in normalized if ch not in string.punctuation and not ch.isspace())


def is_near_duplicate(a: str, b: str) -> bool:
    """İki metnin (noktalama/boşluk/büyük-küçük harf farkı göz ardı edilerek)
    aynı veya birbirinin neredeyse tekrarı olup olmadığını kontrol eder.

    Sahne başlığı ile seçili altyazı metni aynı kısa ifadeyi tekrar ediyorsa
    (ör. ikisi de "Ana Panel"), ekranda aynı bilginin hem üstte hem altta
    görünmesini önlemek için kullanılır. Kısa bir başlığın, çok daha uzun bir
    anlatım (narration) cümlesinin doğal bir alt dizesi olması (ör. başlık
    "Ana Panel", anlatım "Ana panelden sol menüye gidilir...") tekrar
    SAYILMAZ — bu iki farklı ayrıntı düzeyidir, kopya değildir. Bu yüzden
    yalnızca uzunlukları birbirine yakın (oran >= 0.7) metinler alt dize
    kontrolüne tabi tutulur.
    """
    norm_a = _normalize_for_comparison(a)
    norm_b = _normalize_for_comparison(b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True

    shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
    length_ratio = len(shorter) / len(longer)
    if length_ratio < 0.7:
        return False
    return shorter in longer


def draw_subtitle_panel(frame: Image.Image, text: str, font: ImageFont.ImageFont) -> Image.Image:
    """Seçili altyazı metnini (narration veya on_screen_text) alt kısımda
    yarı saydam bir panel üzerinde gösterir. Panel yüksekliği, satır sayısına
    göre dinamik olarak boyutlandırılır (çok satırlı Türkçe metni destekler)."""
    if not text or not text.strip():
        return frame
    frame = frame.convert("RGBA")
    w, h = frame.size
    margin = max(round(w * SAFE_MARGIN_RATIO), 16)
    max_text_width = w - 2 * margin
    lines = wrap_text(text, font, max_text_width)
    if not lines:
        return frame

    line_height = font.size + 8
    panel_height = line_height * len(lines) + 20
    panel_top = max(h - margin - panel_height, 0)

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([margin, panel_top, w - margin, panel_top + panel_height], fill=(0, 0, 0, 165))

    y = panel_top + 10
    for line in lines:
        text_w = font.getlength(line)
        x = max((w - text_w) / 2, margin)
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    return Image.alpha_composite(frame, overlay)


def draw_scene_title(frame: Image.Image, title: str, font: ImageFont.ImageFont) -> Image.Image:
    """scene_title'ı sol üstte, göz yormayan ama ayırt edilebilir bir etiketle gösterir."""
    if not title or not title.strip():
        return frame
    frame = frame.convert("RGBA")
    w, h = frame.size
    margin = max(round(w * SAFE_MARGIN_RATIO), 16)
    padding = 10

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    text_w = font.getlength(title)
    box = [margin, margin, margin + text_w + 2 * padding, margin + font.size + 2 * padding]
    draw.rectangle(box, fill=(20, 20, 20, 150))
    draw.text((margin + padding, margin + padding), title, font=font, fill=(255, 255, 255, 255))

    return Image.alpha_composite(frame, overlay)


def draw_highlight_rect(
    frame: Image.Image,
    rect: HighlightRect,
    color: Tuple[int, int, int, int] = (255, 200, 0, 220),
    border_width: int = 4,
) -> Image.Image:
    """Verilen normalize koordinatlarda basit, görünür bir çerçeve çizer (kare sınırları içinde)."""
    frame = frame.convert("RGBA")
    w, h = frame.size
    x0 = round(rect.x * w)
    y0 = round(rect.y * h)
    x1 = round((rect.x + rect.width) * w)
    y1 = round((rect.y + rect.height) * h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(h - 1, y1)
    if x1 <= x0 or y1 <= y0:
        return frame

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([x0, y0, x1, y1], outline=color, width=border_width)
    return Image.alpha_composite(frame, overlay)


def draw_cursor(frame: Image.Image, position: Tuple[float, float], radius: int = 16) -> Image.Image:
    """Normalize (x, y) konumunda basit bir fare imleci gösterir (AI Görsel Analiz sahneleri için)."""
    frame = frame.convert("RGBA")
    w, h = frame.size
    cx, cy = round(position[0] * w), round(position[1] * h)

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(255, 255, 255, 235),
        outline=(20, 20, 20, 255),
        width=2,
    )
    inner = max(radius // 4, 3)
    draw.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=(220, 30, 90, 255))
    return Image.alpha_composite(frame, overlay)


def draw_click_effect(
    frame: Image.Image, center: Tuple[float, float], progress: float, max_radius_ratio: float = 0.07
) -> Image.Image:
    """Hedef merkezinde genişleyip solan basit bir tıklama (pulse) halkası çizer.

    progress 0'dan 1'e ilerledikçe halka büyür ve saydamlaşır (deterministik).
    """
    frame = frame.convert("RGBA")
    w, h = frame.size
    progress = min(max(progress, 0.0), 1.0)
    cx, cy = round(center[0] * w), round(center[1] * h)
    radius = round(max_radius_ratio * min(w, h) * (0.35 + 0.65 * progress))
    alpha = round(220 * (1.0 - progress))

    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(255, 200, 0, alpha), width=4)
    return Image.alpha_composite(frame, overlay)


# --- Girdi doğrulama -------------------------------------------------------


def validate_video_inputs(storyboard: Dict, screen_bytes: Dict[str, bytes]) -> Dict:
    """Render öncesi storyboard/ekran görüntüsü tutarlılığını deterministik olarak doğrular.

    Döndürür: {"passed": bool, "errors": [...], "warnings": [...]}
    """
    errors: List[str] = []
    warnings: List[str] = []

    scenes = storyboard.get("scenes") or []
    if not scenes:
        errors.append("Storyboard'da en az bir sahne olmalı.")
        return {"passed": False, "errors": errors, "warnings": warnings}

    for scene in scenes:
        image_id = scene.get("image_id")
        if not image_id:
            errors.append("Bir sahnenin image_id değeri eksik.")
            continue

        if image_id not in screen_bytes:
            errors.append(f"{image_id} için ekran görüntüsü baytları bulunamadı.")
        else:
            raw = screen_bytes[image_id]
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    im.verify()
            except Exception:  # noqa: BLE001
                errors.append(f"{image_id} için ekran görüntüsü okunamıyor veya bozuk.")

        duration = scene.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            errors.append(f"{image_id or '?'}: sahne süresi geçersiz.")

    return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}


def check_overlay_content_warnings(storyboard: Dict, settings: VideoSettings) -> List[str]:
    """Etkin bindirmelerin (altyazı/sahne başlığı) her sahnede gösterecek içeriği olup olmadığını kontrol eder.

    Bu bir hata değildir (render yine de çalışır); yalnızca seçili altyazı
    kaynağı boşsa veya sahne başlığı, tekrar koruması nedeniyle otomatik
    olarak gizlenecekse bunu kullanıcıya önceden görünür kılar.
    """
    warnings: List[str] = []
    source_label = SUBTITLE_SOURCE_OPTIONS.get(settings.subtitle_source, settings.subtitle_source)
    for scene in storyboard.get("scenes", []):
        image_id = scene.get("image_id", "?")
        subtitle_text = get_subtitle_text(scene, settings.subtitle_source)

        if settings.subtitle_source != "none" and not subtitle_text:
            field_label = "Anlatım (narration)" if settings.subtitle_source == "narration" else "Ekran üstü metin"
            warnings.append(
                f"{image_id}: Altyazı kaynağı '{source_label}' seçili ancak '{field_label}' boş, "
                "bu sahnede altyazı gösterilmeyecek."
            )

        scene_title_text = scene.get("scene_title", "")
        if settings.scene_titles_enabled and not scene_title_text.strip():
            warnings.append(
                f"{image_id}: Sahne başlıkları etkin ancak 'Sahne başlığı' boş, "
                "bu sahnede başlık gösterilmeyecek."
            )
        elif (
            settings.scene_titles_enabled
            and subtitle_text
            and is_near_duplicate(subtitle_text, scene_title_text)
        ):
            warnings.append(
                f"{image_id}: Sahne başlığı ile seçili altyazı neredeyse aynı olduğundan "
                "bu sahnede başlık otomatik olarak gizlenecek (tekrar önleme)."
            )

        wants_action_effect = scene.get("cursor_enabled") or scene.get("click_effect_enabled")
        if wants_action_effect and not scene.get("highlight_rect"):
            warnings.append(
                f"{image_id}: '{scene.get('action_type', '?')}' eylemi için imleç/tıklama efekti "
                "istendi ancak vurgu (highlight) koordinatı yok; bu sahnede hedef yakınlaştırma, "
                "imleç ve tıklama efekti render edilmeyecek (koordinat uydurulmaz)."
            )

    return warnings


def calculate_expected_duration(storyboard: Dict) -> float:
    """Sahne sürelerinin toplamından (düzenlenmiş storyboard'dan) beklenen süreyi hesaplar."""
    return float(sum(float(s.get("duration_seconds", 0) or 0) for s in storyboard.get("scenes", [])))


# --- Eskime (stale) tespiti -------------------------------------------------


def compute_video_state_fingerprint(storyboard: Dict, settings: VideoSettings) -> str:
    """Storyboard + video ayarlarının bir özetini (hash) üretir.

    Video üretildikten sonra bu değer değişirse üretilen video "eski" (stale)
    sayılır ve kullanıcıya yeniden oluşturması gerektiği bildirilir.
    """
    payload = json.dumps(
        {"storyboard": storyboard, "settings": settings.model_dump()},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- FFmpeg alt süreç yardımcıları -----------------------------------------


def _run_ffmpeg(args: List[str], timeout: int) -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        raise FFmpegProcessError(stderr or f"FFmpeg çıkış kodu {proc.returncode}")


def _probe_duration_seconds(path: Path, timeout: int = 15) -> Optional[float]:
    if not is_ffprobe_available():
        return None
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        return float(proc.stdout.decode("utf-8").strip())
    except Exception:  # noqa: BLE001
        return None


def build_transition_filter_complex(durations: List[float], transitions: List[str]) -> Tuple[str, str]:
    """Sahne segmentlerini birleştiren FFmpeg filter_complex string'ini üretir.

    Saf string üretimidir; FFmpeg çalıştırmaz (test edilebilirlik için ayrı
    tutulur). (filter_complex_string, son_video_etiketi) döner. transitions[0]
    kullanılmaz (ilk sahnenin öncesinde bir geçiş yoktur).

    Üç veya daha fazla `fade` geçişi art arda zincirlendiğinde, bir önceki
    `xfade` düğümünün çıktısı FFmpeg'in dahili AVTB (1/1000000) zaman
    tabanını kullanırken, zincire yeni katılan ham dosya girdisi kendi
    konteyner zaman tabanını (ör. 1/12288) taşır. Bu uyuşmazlık
    "timebase do not match" hatasına yol açar. Bunu önlemek için her ham
    girdi, herhangi bir concat/xfade düğümüne verilmeden önce `settb=AVTB`
    ile aynı zaman tabanına normalize edilir.
    """
    n = len(durations)
    filter_parts: List[str] = []

    # Her ham girdinin zaman tabanını önceden normalize et (bkz. yukarıdaki not).
    for i in range(n):
        filter_parts.append(f"[{i}:v]settb=AVTB[b{i}]")

    current_label = "b0"
    running_duration = durations[0]

    for i in range(1, n):
        next_label = f"v{i}"
        if transitions[i] == "fade":
            offset = max(running_duration - FADE_DURATION_SECONDS, 0.0)
            filter_parts.append(
                f"[{current_label}][b{i}]xfade=transition=fade:"
                f"duration={FADE_DURATION_SECONDS}:offset={offset:.3f}[{next_label}]"
            )
            running_duration = running_duration + durations[i] - FADE_DURATION_SECONDS
        else:
            filter_parts.append(f"[{current_label}][b{i}]concat=n=2:v=1:a=0[{next_label}]")
            running_duration = running_duration + durations[i]
        current_label = next_label

    return ";".join(filter_parts), current_label


def _concat_via_demuxer(segment_paths: List[Path], output_path: Path, timeout: int) -> None:
    list_file = output_path.parent / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in segment_paths:
            safe_path = str(p).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
    _run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output_path)],
        timeout=timeout,
    )


def _concat_via_xfade(
    segment_paths: List[Path], transitions: List[str], durations: List[float], output_path: Path, timeout: int
) -> None:
    filter_complex, final_label = build_transition_filter_complex(durations, transitions)
    inputs: List[str] = []
    for p in segment_paths:
        inputs += ["-i", str(p)]
    _run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            f"[{final_label}]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            str(output_path),
        ],
        timeout=timeout,
    )


def _concatenate_segments(
    segment_paths: List[Path], transitions: List[str], durations: List[float], output_path: Path, timeout: int
) -> None:
    if len(segment_paths) == 1 or all(t != "fade" for t in transitions[1:]):
        _concat_via_demuxer(segment_paths, output_path, timeout)
    else:
        _concat_via_xfade(segment_paths, transitions, durations, output_path, timeout)


# --- Sahne segmenti render ---------------------------------------------------


def _safe_segment_slug(text: str) -> str:
    """Segment dosya adı için güvenli (yol geçişi içermeyen) bir kısa etiket üretir."""
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "scene"


def _render_scene_segment(
    scene: Dict,
    screenshot_bytes: bytes,
    settings: VideoSettings,
    tmp_dir: Path,
    scene_index: int,
    timeout: int,
) -> Path:
    target_size = settings.resolution_tuple
    # scene_id, aynı image_id'nin birden fazla sahnede (Faz 4C alt sahne
    # genişletmesi) tekrarlanabildiği durumlarda segment dosyalarının
    # birbirinin üzerine yazılmamasını garanti eder; scene_id yoksa (eski
    # storyboard) image_id'ye geri düşülür (geriye dönük uyumluluk).
    segment_label = _safe_segment_slug(scene.get("scene_id") or scene.get("image_id", "scene"))
    frames_dir = tmp_dir / f"scene_{scene_index:03d}_{segment_label}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(io.BytesIO(screenshot_bytes)) as src:
        src.load()
        base = fit_image_to_canvas(src, target_size)

    highlight_rect = normalize_highlight_rect(scene.get("highlight_rect"))
    focus = (
        (highlight_rect.x + highlight_rect.width / 2, highlight_rect.y + highlight_rect.height / 2)
        if highlight_rect
        else (0.5, 0.5)
    )

    title_font = _load_font(max(round(target_size[1] * 0.045), 14))
    subtitle_font = _load_font(max(round(target_size[1] * 0.04), 14))

    scene_title_text = scene.get("scene_title", "")
    subtitle_text = get_subtitle_text(scene, settings.subtitle_source)

    # Tekrar (duplication) koruması: seçili altyazı, sahne başlığıyla aynı ya
    # da neredeyse aynıysa (ör. ikisi de "Ana Panel"), aynı bilginin hem
    # üstte hem altta görünmesini önlemek için başlık bu sahnede gizlenir.
    # Altyazı her zaman korunur — tek sahneli videolar dahil geçerli bir
    # anlatım altyazısı yalnızca sahne sayısı yüzünden kaldırılmaz.
    show_scene_title = settings.scene_titles_enabled
    if show_scene_title and subtitle_text and is_near_duplicate(subtitle_text, scene_title_text):
        show_scene_title = False

    # AI Görsel Analiz Modu sahneleri: imleç/tıklama efekti yalnızca bir
    # vurgu koordinatı GERÇEKTEN varsa render edilir; koordinat yoksa hiçbir
    # şey uydurulmaz (bkz. check_overlay_content_warnings uyarısı).
    cursor_enabled = bool(scene.get("cursor_enabled")) and highlight_rect is not None and settings.highlight_enabled
    click_effect_enabled = (
        bool(scene.get("click_effect_enabled")) and highlight_rect is not None and settings.highlight_enabled
    )
    click_effect_start_frame = max(NUM_ZOOM_KEYFRAMES - 3, 0)

    for i in range(NUM_ZOOM_KEYFRAMES):
        progress = i / max(NUM_ZOOM_KEYFRAMES - 1, 1)
        if settings.zoom_enabled:
            frame = apply_zoom(base, progress, focus)
        else:
            frame = base.copy()

        if settings.highlight_enabled and highlight_rect is not None:
            frame = draw_highlight_rect(frame, highlight_rect)
        if cursor_enabled:
            cursor_pos = (0.5 + (focus[0] - 0.5) * progress, 0.5 + (focus[1] - 0.5) * progress)
            frame = draw_cursor(frame, cursor_pos)
        if click_effect_enabled and i >= click_effect_start_frame:
            click_progress = (i - click_effect_start_frame) / max(
                NUM_ZOOM_KEYFRAMES - 1 - click_effect_start_frame, 1
            )
            frame = draw_click_effect(frame, focus, click_progress)
        if show_scene_title:
            frame = draw_scene_title(frame, scene_title_text, title_font)
        if subtitle_text:
            frame = draw_subtitle_panel(frame, subtitle_text, subtitle_font)

        frame.convert("RGB").save(frames_dir / f"frame_{i:03d}.png")

    duration = float(scene["duration_seconds"])
    input_framerate = NUM_ZOOM_KEYFRAMES / duration
    segment_path = tmp_dir / f"scene_{scene_index:03d}_{segment_label}.mp4"
    _run_ffmpeg(
        [
            "-framerate",
            f"{input_framerate:.6f}",
            "-i",
            str(frames_dir / "frame_%03d.png"),
            "-vf",
            f"fps={settings.fps},format=yuv420p",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            str(segment_path),
        ],
        timeout=timeout,
    )
    return segment_path


# --- Üst düzey sonuç ve giriş noktası ----------------------------------------


@dataclass
class VideoGenerationResult:
    success: bool
    video_bytes: Optional[bytes] = None
    error: Optional[str] = None
    expected_duration_seconds: float = 0.0
    actual_duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    generation_seconds: Optional[float] = None
    encoder: str = "ffmpeg (libx264)"
    ffmpeg_available: bool = True
    temp_files_cleaned: bool = True
    scene_count: int = 0


def generate_video(
    storyboard: Dict,
    screen_bytes: Dict[str, bytes],
    settings: VideoSettings,
) -> VideoGenerationResult:
    """Storyboard + gerçek ekran görüntüsü baytlarından deterministik, sessiz bir MP4 üretir.

    Hiçbir üretici video/görsel modeli çağırmaz. Tüm ara dosyalar geçici bir
    dizinde tutulur ve başarı/başarısızlık fark etmeksizin temizlenir.
    """
    if not is_ffmpeg_available():
        return VideoGenerationResult(success=False, error=FFMPEG_MISSING_MESSAGE, ffmpeg_available=False)

    validation = validate_video_inputs(storyboard, screen_bytes)
    if not validation["passed"]:
        return VideoGenerationResult(
            success=False,
            error="Video girdi doğrulaması başarısız: " + "; ".join(validation["errors"]),
        )

    scenes = sorted(storyboard["scenes"], key=lambda s: s["scene_number"])
    expected_duration = calculate_expected_duration(storyboard)
    timeout = get_encoding_timeout_seconds()

    start = time.perf_counter()
    tmp_dir = Path(tempfile.mkdtemp(prefix="a1_video_"))
    result: VideoGenerationResult

    try:
        segment_paths: List[Path] = []
        for idx, scene in enumerate(scenes):
            raw = screen_bytes[scene["image_id"]]
            segment_paths.append(_render_scene_segment(scene, raw, settings, tmp_dir, idx, timeout))

        # Tekrarlanan image_id'ler dahil, her storyboard sahnesi tam olarak bir
        # segment üretmelidir; bu bir güvenlik ağıdır (render mantığı zaten
        # her sahne için ayrı bir dosya adı üretir).
        assert len(segment_paths) == len(scenes), (
            f"Üretilen segment sayısı ({len(segment_paths)}) sahne sayısıyla "
            f"({len(scenes)}) eşleşmiyor."
        )

        durations = [float(s["duration_seconds"]) for s in scenes]
        transitions = [s.get("transition", "cut") for s in scenes]
        final_path = tmp_dir / "final_output.mp4"
        _concatenate_segments(segment_paths, transitions, durations, final_path, timeout)

        video_bytes = final_path.read_bytes()
        actual_duration = _probe_duration_seconds(final_path)

        result = VideoGenerationResult(
            success=True,
            video_bytes=video_bytes,
            expected_duration_seconds=expected_duration,
            actual_duration_seconds=actual_duration,
            file_size_bytes=len(video_bytes),
            generation_seconds=time.perf_counter() - start,
            encoder="ffmpeg (libx264)",
            ffmpeg_available=True,
            scene_count=len(scenes),
        )
    except subprocess.TimeoutExpired:
        result = VideoGenerationResult(
            success=False,
            error=f"Video kodlama {timeout} saniye içinde tamamlanmadı ve güvenli biçimde durduruldu.",
            expected_duration_seconds=expected_duration,
            scene_count=len(scenes),
        )
    except FFmpegProcessError as exc:
        result = VideoGenerationResult(
            success=False,
            error=f"FFmpeg işlemi başarısız oldu: {exc}",
            expected_duration_seconds=expected_duration,
            scene_count=len(scenes),
        )
    except Exception as exc:  # noqa: BLE001 - beklenmeyen hata da kullanıcıya güvenle bildirilir
        result = VideoGenerationResult(
            success=False,
            error=f"Video üretimi sırasında beklenmeyen bir hata oluştu: {exc}",
            expected_duration_seconds=expected_duration,
            scene_count=len(scenes),
        )
    finally:
        cleaned = True
        try:
            shutil.rmtree(tmp_dir, ignore_errors=False)
        except Exception:  # noqa: BLE001
            cleaned = False

    result.temp_files_cleaned = cleaned
    return result
