"""C1 otomatik Journey oluşturma için Pydantic şemaları ve doğrulama kuralları."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, field_validator, model_validator


class JourneyActivityItem(BaseModel):
    activity_id: str
    order: int
    reason: str
    estimated_minutes: int

    @field_validator("activity_id", "reason")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("estimated_minutes")
    @classmethod
    def positive_minutes(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("estimated_minutes pozitif olmalı")
        return v


class JourneyOutput(BaseModel):
    audience_fit_summary: str
    journey_activities: List[JourneyActivityItem]
    total_minutes: int
    strategy_summary: str

    @field_validator("audience_fit_summary", "strategy_summary")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("total_minutes")
    @classmethod
    def positive_total(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("total_minutes pozitif olmalı")
        return v

    @model_validator(mode="after")
    def check_activities(self) -> "JourneyOutput":
        if not self.journey_activities:
            raise ValueError("journey_activities boş olamaz")

        activity_ids = [a.activity_id for a in self.journey_activities]
        if len(activity_ids) != len(set(activity_ids)):
            raise ValueError("Aynı aktivite birden fazla kez seçilemez")

        orders = sorted(a.order for a in self.journey_activities)
        if len(orders) != len(set(orders)):
            raise ValueError("order değerleri benzersiz olmalı")
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("order değerleri 1'den başlayarak ardışık olmalı")

        return self


def validate_c1_output(data: dict) -> JourneyOutput:
    """JourneyOutput şemasına göre doğrular. Hata durumunda ValidationError/ValueError fırlatır."""
    return JourneyOutput.model_validate(data)
