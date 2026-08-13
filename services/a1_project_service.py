"""A1 eğitim videosu projesi için görsel doğrulama ve sahne listesi yardımcıları.

Bu modül Streamlit'ten bağımsızdır; yalnızca görsel okuma/boyut çıkarma ve
sahne listesi üzerinde sıralama/kaldırma işlemlerini içerir. Storyboard veya
video üretimiyle ilgili hiçbir mantık burada yoktur.
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional, Tuple

from PIL import Image

SUPPORTED_EXTENSIONS = ("png", "jpg", "jpeg")


def generate_image_id(order: int) -> str:
    """Yükleme sırasına göre kararlı bir image_id üretir (screen_01, screen_02, ...)."""
    return f"screen_{order:02d}"


def validate_image_extension(filename: str) -> Optional[str]:
    """Uzantı desteklenmiyorsa Türkçe hata mesajı, destekleniyorsa None döner."""
    lower = filename.lower()
    if not any(lower.endswith(f".{ext}") for ext in SUPPORTED_EXTENSIONS):
        return (
            f"Desteklenmeyen dosya uzantısı: {filename}. "
            "Yalnızca PNG, JPG veya JPEG dosyaları desteklenir."
        )
    return None


def read_image_dimensions(file_bytes: bytes, filename: str) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    """Görsel baytlarını doğrular ve (genişlik, yükseklik) döner.

    Bozuk veya okunamayan görseller için açık bir Türkçe hata mesajı döner;
    istisna fırlatmaz.
    """
    ext_error = validate_image_extension(filename)
    if ext_error:
        return None, ext_error

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
    except Exception:  # noqa: BLE001 - herhangi bir bozuk görsel kullanıcıya bildirilir
        return None, f"Görsel bozuk veya okunamıyor: {filename}"

    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
    except Exception:  # noqa: BLE001
        return None, f"Görsel boyutları okunamadı: {filename}"

    return (width, height), None


def _renumber(screens: List[Dict]) -> List[Dict]:
    for idx, screen in enumerate(screens):
        screen["order"] = idx + 1
    return screens


def move_screen_up(screens: List[Dict], index: int) -> List[Dict]:
    """Belirtilen konumdaki sahneyi bir yukarı taşır ve sıraları yeniden numaralandırır."""
    if index <= 0 or index >= len(screens):
        return screens
    screens[index - 1], screens[index] = screens[index], screens[index - 1]
    return _renumber(screens)


def move_screen_down(screens: List[Dict], index: int) -> List[Dict]:
    """Belirtilen konumdaki sahneyi bir aşağı taşır ve sıraları yeniden numaralandırır."""
    if index < 0 or index >= len(screens) - 1:
        return screens
    screens[index + 1], screens[index] = screens[index], screens[index + 1]
    return _renumber(screens)


def remove_screen(screens: List[Dict], index: int) -> List[Dict]:
    """Belirtilen konumdaki sahneyi kaldırır ve kalan sıraları yeniden numaralandırır."""
    if index < 0 or index >= len(screens):
        return screens
    screens.pop(index)
    return _renumber(screens)
