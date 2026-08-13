"""A2 destek/onboarding chatbot için Pydantic şemaları ve doğrulama kuralları."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator


class A2Output(BaseModel):
    answer: str
    source_ids: List[str] = Field(default_factory=list)
    escalation_recommended: bool
    support_reason: str

    @field_validator("answer", "support_reason")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, v: List[str]) -> List[str]:
        if len(v) != len(set(v)):
            raise ValueError("source_ids içinde tekrarlanan kimlik olamaz")
        return v


def validate_a2_output(data: dict) -> A2Output:
    """A2Output şemasına göre doğrular. Hata durumunda ValidationError/ValueError fırlatır."""
    return A2Output.model_validate(data)
