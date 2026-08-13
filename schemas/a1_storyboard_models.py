"""A1 storyboard üretimi için Pydantic şemaları ve yapısal doğrulama kuralları.

Bu şema yalnızca modelin JSON çıktısının beklenen yapıya (alanlar, veri
tipleri, sayısal sınırlar) uyup uymadığını kontrol eder. Kaynak ekranlarla
tutarlılık (sıra korunması, her ekranın en az bir kez kullanılması, toplam
sürenin doğruluğu vb.) ayrı bir deterministik katmanda
(`services/a1_storyboard_validation.py`) kontrol edilir.

Faz 4C: Bir ekran görüntüsü (image_id) artık BİRDEN FAZLA sahnede
(alt sahne genişletmesi) kullanılabilir; bu yüzden benzersizlik kuralı artık
image_id yerine yeni zorunlu `scene_id` alanına uygulanır. Eski (Faz 4C
öncesi) storyboard JSON'ları scene_id İÇERMEZ; bu tür veriler doğrudan
`validate_storyboard`'a verilmeden önce
`services/a1_storyboard_service.py::migrate_scene_ids` ile deterministik
olarak göç ettirilmelidir.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_TRANSITIONS = {"fade", "cut"}
ALLOWED_ACTION_TYPES = {"click", "enter_text", "select", "review", "information"}
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 14
MAX_ON_SCREEN_TEXT_LENGTH = 40


class StoryboardScene(BaseModel):
    scene_id: str
    scene_number: int
    image_id: str
    scene_title: str
    duration_seconds: float
    narration: str
    on_screen_text: str
    transition: str
    zoom_enabled: bool
    highlight_description: str
    requires_review: bool
    # Faz 4B/4C'de eklenen alanlar; metinden üretilen (safe/assisted mod)
    # eski storyboard'larda bulunmaz, bu yüzden hepsi opsiyoneldir.
    highlight_rect: Optional[dict] = None
    action_type: Optional[str] = None
    target_label: Optional[str] = None
    instruction_text: Optional[str] = None
    cursor_enabled: bool = False
    click_effect_enabled: bool = False
    matched_screen_id: Optional[str] = None
    target_element_id: Optional[str] = None
    grounding_source_ids: List[str] = Field(default_factory=list)
    grounding_warnings: List[str] = Field(default_factory=list)
    recommended_duration_seconds: Optional[float] = None
    duration_source: Optional[str] = None

    @field_validator("scene_id", "image_id", "scene_title", "narration", "on_screen_text", "highlight_description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("scene_number")
    @classmethod
    def positive_scene_number(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("scene_number pozitif olmalı")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def duration_within_limits(cls, v: float) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("duration_seconds bir sayı olmalı")
        if not (MIN_DURATION_SECONDS <= v <= MAX_DURATION_SECONDS):
            raise ValueError(
                f"duration_seconds {MIN_DURATION_SECONDS} ile {MAX_DURATION_SECONDS} arasında olmalı"
            )
        return float(v)

    @field_validator("on_screen_text")
    @classmethod
    def on_screen_text_length(cls, v: str) -> str:
        if len(v) > MAX_ON_SCREEN_TEXT_LENGTH:
            raise ValueError(f"on_screen_text en fazla {MAX_ON_SCREEN_TEXT_LENGTH} karakter olmalı")
        return v

    @field_validator("transition")
    @classmethod
    def valid_transition(cls, v: str) -> str:
        if v not in ALLOWED_TRANSITIONS:
            raise ValueError("transition yalnızca 'fade' veya 'cut' olabilir")
        return v

    @field_validator("action_type")
    @classmethod
    def valid_action_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_ACTION_TYPES:
            raise ValueError(
                f"Geçersiz action_type: {v}. Geçerli değerler: {', '.join(sorted(ALLOWED_ACTION_TYPES))}"
            )
        return v


class Storyboard(BaseModel):
    title: str
    target_audience: str
    tone: str
    scenes: List[StoryboardScene]
    total_duration_seconds: float
    closing_text: str

    @field_validator("title", "target_audience", "tone", "closing_text")
    @classmethod
    def not_blank_top(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("total_duration_seconds")
    @classmethod
    def positive_total_duration(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("total_duration_seconds pozitif olmalı")
        return float(v)

    @model_validator(mode="after")
    def check_scenes(self) -> "Storyboard":
        if not self.scenes:
            raise ValueError("scenes boş olamaz")

        scene_ids = [s.scene_id for s in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("scene_id değerleri benzersiz olmalı")

        scene_numbers = sorted(s.scene_number for s in self.scenes)
        if len(scene_numbers) != len(set(scene_numbers)):
            raise ValueError("scene_number değerleri benzersiz olmalı")
        if scene_numbers != list(range(1, len(scene_numbers) + 1)):
            raise ValueError("scene_number değerleri 1'den başlayarak ardışık olmalı")

        return self


def validate_storyboard(data: dict) -> Storyboard:
    """Storyboard şemasına göre doğrular. Hata durumunda ValidationError fırlatır.

    Girdi scene_id içermiyorsa (Faz 4C öncesi eski storyboard), önce
    `services/a1_storyboard_service.py::migrate_scene_ids` ile göç
    ettirilmelidir; bu fonksiyon scene_id'yi zorunlu kabul eder.
    """
    return Storyboard.model_validate(data)
