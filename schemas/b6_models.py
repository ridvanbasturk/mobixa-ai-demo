"""B6 rapor değerlendirmesi için Pydantic şemaları ve doğrulama kuralları."""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, field_validator, model_validator

Severity = Literal["low", "medium", "high"]


class Insight(BaseModel):
    title: str
    finding: str
    evidence: str
    recommendation: str
    severity: Severity

    @field_validator("title", "finding", "evidence", "recommendation")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v


class B6Output(BaseModel):
    executive_summary: str
    insights: List[Insight]

    @field_validator("executive_summary")
    @classmethod
    def summary_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("executive_summary boş olamaz")
        return v

    @model_validator(mode="after")
    def check_insights(self) -> "B6Output":
        if len(self.insights) != 4:
            raise ValueError(f"Tam olarak 4 değerlendirme üretilmeli, üretilen: {len(self.insights)}")

        titles = [i.title.strip().lower() for i in self.insights]
        if len(titles) != len(set(titles)):
            raise ValueError("Aynı başlıkta birden fazla değerlendirme olamaz")

        return self


def validate_b6_output(data: dict) -> B6Output:
    """B6Output şemasına göre doğrular. Hata durumunda ValidationError/ValueError fırlatır."""
    return B6Output.model_validate(data)
