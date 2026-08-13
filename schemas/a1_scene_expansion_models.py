"""A1 Faz 4C — grounded ekran sonucunun birden fazla alt sahneye (sub-scene)
genişletilmesi için Pydantic şemaları.

Bu şema yalnızca modelin JSON çıktısının yapısal olarak geçerli olduğunu
doğrular (alanlar, action_type, on_screen_text uzunluğu, en fazla 4 alt
sahne). target_element_id'nin eşleşen ekrana ait olması, grounding_source_ids
geçerliliği, kaçınılması gereken terminoloji gibi bilgi tabanına dayalı
(deterministik) kontroller `services/a1_vision_validation.py::
validate_scene_expansion_result` içinde yapılır.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.a1_vision_models import ACTION_TYPES, MAX_ON_SCREEN_TEXT_LENGTH, VisionHighlightRect

MAX_SUB_SCENES_PER_IMAGE = 4


class SubScene(BaseModel):
    """Tek bir ekran görüntüsünden üretilen, tek bir onaylı hedefe/eyleme
    odaklanan alt sahne. requires_review, ayrıştırma sonrası uygulama
    tarafından her zaman True olarak zorlanır (bkz. a1_scene_expansion_service)."""

    sub_scene_key: str
    scene_title: str
    target_element_id: Optional[str] = None
    action_type: str
    instruction_text: str
    narration: str
    on_screen_text: str
    highlight_description: str
    highlight_rect: Optional[VisionHighlightRect] = None
    cursor_enabled: bool = False
    click_effect_enabled: bool = False
    requires_review: bool = True
    grounding_source_ids: List[str] = Field(default_factory=list)

    @field_validator("sub_scene_key", "scene_title", "instruction_text", "narration", "highlight_description")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("on_screen_text")
    @classmethod
    def on_screen_text_valid(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("on_screen_text boş olamaz")
        if len(v) > MAX_ON_SCREEN_TEXT_LENGTH:
            raise ValueError(f"on_screen_text en fazla {MAX_ON_SCREEN_TEXT_LENGTH} karakter olmalı")
        return v

    @field_validator("grounding_source_ids")
    @classmethod
    def must_be_list(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("grounding_source_ids bir liste olmalı")
        return v

    @field_validator("action_type")
    @classmethod
    def valid_action_type(cls, v: str) -> str:
        if v not in ACTION_TYPES:
            raise ValueError(
                f"Geçersiz action_type: {v}. Geçerli değerler: {', '.join(sorted(ACTION_TYPES))}"
            )
        return v


class SceneExpansionResult(BaseModel):
    """Tek bir ekran görüntüsü için üretilen bir veya daha fazla alt sahne."""

    image_id: str
    sub_scenes: List[SubScene]

    @field_validator("image_id")
    @classmethod
    def not_blank_image_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("image_id boş olamaz")
        return v

    @model_validator(mode="after")
    def check_sub_scenes(self) -> "SceneExpansionResult":
        if not self.sub_scenes:
            raise ValueError("sub_scenes boş olamaz (en az bir alt sahne gerekir)")
        if len(self.sub_scenes) > MAX_SUB_SCENES_PER_IMAGE:
            raise ValueError(f"Bir ekrandan en fazla {MAX_SUB_SCENES_PER_IMAGE} alt sahne üretilebilir")

        keys = [s.sub_scene_key for s in self.sub_scenes]
        if len(keys) != len(set(keys)):
            raise ValueError("sub_scene_key değerleri bu ekran içinde benzersiz olmalı")

        return self


def validate_scene_expansion_result(data: dict) -> SceneExpansionResult:
    """SceneExpansionResult şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return SceneExpansionResult.model_validate(data)
