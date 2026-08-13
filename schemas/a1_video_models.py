"""A1 yerel MP4 üretimi için Pydantic şemaları.

Bu şemalar yalnızca video ayarlarının (çözünürlük, FPS, dosya adı) ve
opsiyonel normalize edilmiş vurgu (highlight) dikdörtgeninin yapısal olarak
geçerli olduğunu doğrular. Storyboard'un kendisiyle (sahne sayısı, sıra,
ekran görüntüsü eşleşmesi) tutarlılık `services/a1_video_service.py`
içindeki deterministik doğrulama fonksiyonlarında kontrol edilir.
"""
from __future__ import annotations

from typing import Tuple

from pydantic import BaseModel, field_validator, model_validator

RESOLUTION_OPTIONS = {
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
}
DEFAULT_RESOLUTION = "1280x720"

FPS_OPTIONS = (24, 30)
DEFAULT_FPS = 24

# Altyazı panelinde hangi sahne alanının gösterileceğini belirler:
# - "narration": tam anlatım cümlesi (seslendirme metni, varsayılan)
# - "on_screen_text": kısa ekran üstü çağrı metni
# - "none": altyazı paneli hiç çizilmez
SUBTITLE_SOURCE_OPTIONS = {
    "narration": "Anlatım metni",
    "on_screen_text": "Kısa ekran metni",
    "none": "Altyazı gösterme",
}
DEFAULT_SUBTITLE_SOURCE = "narration"


class HighlightRect(BaseModel):
    """Ekran görüntüsü üzerinde normalize edilmiş (0-1 arası) bir vurgu alanı.

    Faz 3'te storyboard şeması bu koordinatları içermez; bu model yalnızca
    ileride bir sahneye koordinat eklenirse (ör. manuel JSON düzenlemesiyle)
    render katmanının bunu kullanabilmesi için mimariyi hazırlar.
    """

    x: float
    y: float
    width: float
    height: float

    @field_validator("x", "y")
    @classmethod
    def coordinate_within_bounds(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("x/y değerleri 0 ile 1 arasında olmalı")
        return v

    @model_validator(mode="after")
    def check_size_and_bounds(self) -> "HighlightRect":
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width/height pozitif olmalı")
        if self.x + self.width > 1.0 + 1e-6:
            raise ValueError("x + width 1'i aşamaz")
        if self.y + self.height > 1.0 + 1e-6:
            raise ValueError("y + height 1'i aşamaz")
        return self


class VideoSettings(BaseModel):
    resolution: str = DEFAULT_RESOLUTION
    fps: int = DEFAULT_FPS
    subtitle_source: str = DEFAULT_SUBTITLE_SOURCE
    scene_titles_enabled: bool = True
    zoom_enabled: bool = True
    highlight_enabled: bool = True
    output_filename: str

    @field_validator("resolution")
    @classmethod
    def valid_resolution(cls, v: str) -> str:
        if v not in RESOLUTION_OPTIONS:
            raise ValueError(
                f"Geçersiz çözünürlük: {v}. Geçerli değerler: {', '.join(RESOLUTION_OPTIONS)}"
            )
        return v

    @field_validator("fps")
    @classmethod
    def valid_fps(cls, v: int) -> int:
        if v not in FPS_OPTIONS:
            raise ValueError(f"Geçersiz FPS: {v}. Geçerli değerler: {FPS_OPTIONS}")
        return v

    @field_validator("subtitle_source")
    @classmethod
    def valid_subtitle_source(cls, v: str) -> str:
        if v not in SUBTITLE_SOURCE_OPTIONS:
            raise ValueError(
                f"Geçersiz altyazı kaynağı: {v}. Geçerli değerler: {', '.join(SUBTITLE_SOURCE_OPTIONS)}"
            )
        return v

    @field_validator("output_filename")
    @classmethod
    def not_blank_filename(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Çıktı dosya adı boş olamaz")
        return v

    @property
    def resolution_tuple(self) -> Tuple[int, int]:
        return RESOLUTION_OPTIONS[self.resolution]


def validate_video_settings(data: dict) -> VideoSettings:
    """VideoSettings şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return VideoSettings.model_validate(data)
