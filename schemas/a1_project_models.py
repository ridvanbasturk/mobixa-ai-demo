"""A1 eğitim videosu proje girdileri için Pydantic şemaları.

Bu aşamada yalnızca proje girdileri (ekran görüntüsü meta verisi + sahne
notları) doğrulanır; storyboard veya video üretimi bu şemanın kapsamı
dışındadır.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator

TARGET_AUDIENCES = {"Learner", "Trainer", "Admin"}
TONES = {"Kısa ve doğrudan", "Eğitici", "Kurumsal"}
WORKING_MODES = {"safe", "assisted"}


class TutorialScreen(BaseModel):
    image_id: str
    original_file_name: str
    scene_label: Optional[str] = None
    note: str
    order: int
    width: int
    height: int

    @field_validator("image_id", "original_file_name", "note")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("order", "width", "height")
    @classmethod
    def positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Değer pozitif bir tam sayı olmalı")
        return v


class TutorialProject(BaseModel):
    title: str
    target_audience: str
    tone: str
    working_mode: str
    screens: List[TutorialScreen]

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Video başlığı boş olamaz")
        return v

    @field_validator("target_audience")
    @classmethod
    def valid_audience(cls, v: str) -> str:
        if v not in TARGET_AUDIENCES:
            raise ValueError(
                f"Geçersiz hedef kitle: {v}. Geçerli değerler: {', '.join(sorted(TARGET_AUDIENCES))}"
            )
        return v

    @field_validator("tone")
    @classmethod
    def valid_tone(cls, v: str) -> str:
        if v not in TONES:
            raise ValueError(f"Geçersiz ton: {v}. Geçerli değerler: {', '.join(sorted(TONES))}")
        return v

    @field_validator("working_mode")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        if v not in WORKING_MODES:
            raise ValueError(f"Geçersiz çalışma modu: {v}. Geçerli değerler: {', '.join(sorted(WORKING_MODES))}")
        return v

    @model_validator(mode="after")
    def check_screens(self) -> "TutorialProject":
        if not self.screens:
            raise ValueError("En az bir sahne (ekran görüntüsü) gereklidir")

        image_ids = [s.image_id for s in self.screens]
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("image_id değerleri benzersiz olmalı")

        orders = sorted(s.order for s in self.screens)
        if len(orders) != len(set(orders)):
            raise ValueError("order değerleri benzersiz olmalı")
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("order değerleri 1'den başlayarak ardışık olmalı")

        return self


def validate_tutorial_project(data: dict) -> TutorialProject:
    """TutorialProject şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return TutorialProject.model_validate(data)
