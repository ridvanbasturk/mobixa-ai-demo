"""B1 içerik üretimi için Pydantic şemaları ve doğrulama kuralları."""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Difficulty = Literal["easy", "medium", "hard"]


class MCQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: int
    explanation: str
    source_quote: str
    difficulty: Difficulty
    category: str

    @field_validator("question", "explanation", "source_quote", "category")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("options")
    @classmethod
    def exactly_four_options(cls, v: List[str]) -> List[str]:
        if len(v) != 4:
            raise ValueError("Her soruda tam dört seçenek olmalı")
        if any(not opt or not opt.strip() for opt in v):
            raise ValueError("Seçenekler boş olamaz")
        return v

    @field_validator("correct_answer")
    @classmethod
    def correct_answer_range(cls, v: int) -> int:
        if v < 1 or v > 4:
            raise ValueError("correct_answer 1 ile 4 arasında olmalı")
        return v


class LearningCard(BaseModel):
    title: str
    content: str
    key_takeaway: str

    @field_validator("title", "content", "key_takeaway")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v


class B1Output(BaseModel):
    title: str
    questions: List[MCQuestion]
    learning_cards: List[LearningCard] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_questions(self) -> "B1Output":
        texts = [q.question.strip().lower() for q in self.questions]
        if len(texts) != len(set(texts)):
            raise ValueError("Aynı soru tekrar edilmemeli")
        return self


def validate_b1_output(
    data: dict,
    expected_question_count: int,
    expect_learning_cards: bool,
) -> B1Output:
    """B1Output şemasına göre doğrula ve iş kurallarını kontrol et.

    Hata durumunda pydantic.ValidationError veya ValueError fırlatır.
    """
    result = B1Output.model_validate(data)

    if len(result.questions) != expected_question_count:
        raise ValueError(
            f"Soru sayısı istekle eşleşmiyor: beklenen {expected_question_count}, "
            f"üretilen {len(result.questions)}"
        )

    if expect_learning_cards and len(result.learning_cards) < 1:
        raise ValueError("Öğrenme kartı istendi ancak hiç kart üretilmedi")

    return result
