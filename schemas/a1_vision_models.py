"""A1 AI Görsel Analiz Modu için Pydantic şemaları.

Bu şema yalnızca bir çok-modlu (multimodal) modelin tek bir ekran
görüntüsü için ürettiği analiz JSON'unun yapısal olarak geçerli olduğunu
doğrular. İstenen ekranla eşleşme, vurgu koordinatlarının görsel sınırları
içinde kalması, güven skoru uyarıları gibi deterministik/anlamsal
kontroller `services/a1_vision_validation.py` içinde yapılır.

Faz 4B, tek aşamalı `VisionSceneResult` akışının yanına, bilgi tabanına
bağlı (grounded) iki aşamalı bir akış ekler:
  - Aşama 1 (`VisualObservation`): yalnızca görsel gözlem, ürün davranışı
    açıklaması YOKTUR.
  - Aşama 2 (`GroundedSceneResult`): gözlem + deterministik ekran/öğe
    eşleştirmesi + onaylı bilgi tabanı bağlamından üretilen nihai sahne.
Eski `VisionSceneResult` akışı geriye dönük uyumluluk için olduğu gibi
korunur.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ACTION_TYPES = {"click", "enter_text", "select", "review", "information"}
PRELIMINARY_ACTION_TYPES = ACTION_TYPES | {"unknown"}
MAX_ON_SCREEN_TEXT_LENGTH = 40


class VisionHighlightRect(BaseModel):
    """Ekran görüntüsü üzerinde normalize edilmiş (0-1 arası) bir vurgu alanı."""

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
    def check_size_and_bounds(self) -> "VisionHighlightRect":
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width/height pozitif olmalı")
        if self.x + self.width > 1.0 + 1e-6:
            raise ValueError("x + width 1'i aşamaz")
        if self.y + self.height > 1.0 + 1e-6:
            raise ValueError("y + height 1'i aşamaz")
        return self


class VisionSceneResult(BaseModel):
    image_id: str
    scene_title: str
    visible_ui_elements: List[str]
    primary_target: str
    action_type: str
    instruction_text: str
    narration: str
    on_screen_text: str
    highlight_description: str
    highlight_rect: Optional[VisionHighlightRect] = None
    confidence: float
    requires_review: bool

    @field_validator(
        "image_id", "scene_title", "primary_target", "instruction_text", "narration", "highlight_description"
    )
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

    @field_validator("visible_ui_elements")
    @classmethod
    def elements_is_list(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("visible_ui_elements bir liste olmalı")
        return v

    @field_validator("action_type")
    @classmethod
    def valid_action_type(cls, v: str) -> str:
        if v not in ACTION_TYPES:
            raise ValueError(
                f"Geçersiz action_type: {v}. Geçerli değerler: {', '.join(sorted(ACTION_TYPES))}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("confidence bir sayı olmalı")
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence 0 ile 1 arasında olmalı")
        return float(v)


def validate_vision_scene_result(data: dict) -> VisionSceneResult:
    """VisionSceneResult şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return VisionSceneResult.model_validate(data)


class VisualObservation(BaseModel):
    """Faz 4B Aşama 1: yalnızca görsel gözlem. Ürün davranışı açıklaması içermez."""

    image_id: str
    visible_ui_elements: List[str] = Field(default_factory=list)
    detected_visible_labels: List[str] = Field(default_factory=list)
    possible_primary_target: str
    preliminary_action_type: str
    preliminary_highlight_rect: Optional[VisionHighlightRect] = None
    confidence: float
    visual_uncertainties: List[str] = Field(default_factory=list)

    @field_validator("image_id", "possible_primary_target")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("visible_ui_elements", "detected_visible_labels", "visual_uncertainties")
    @classmethod
    def must_be_list(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("Bu alan bir liste olmalı")
        return v

    @field_validator("preliminary_action_type")
    @classmethod
    def valid_preliminary_action_type(cls, v: str) -> str:
        if v not in PRELIMINARY_ACTION_TYPES:
            raise ValueError(
                f"Geçersiz preliminary_action_type: {v}. "
                f"Geçerli değerler: {', '.join(sorted(PRELIMINARY_ACTION_TYPES))}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("confidence bir sayı olmalı")
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence 0 ile 1 arasında olmalı")
        return float(v)


def validate_visual_observation(data: dict) -> VisualObservation:
    """VisualObservation şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return VisualObservation.model_validate(data)


class GroundedSceneResult(BaseModel):
    """Faz 4B Aşama 2: bilgi tabanına bağlı (grounded) nihai sahne sonucu.

    matched_screen_id / matched_screen_name / screen_match_score /
    target_element_id / grounding_source_ids alanları modelin serbest
    metin üretimine GÜVENİLMEZ; bu alanlar model yanıtı ayrıştırıldıktan
    HEMEN SONRA, `services/a1_vision_service.py::run_grounded_vision_analysis`
    içinde deterministik eşleştirme sonuçlarıyla ÜZERİNE YAZILIR. Şemada
    bulunmalarının nedeni, aşağı akış (storyboard/video) kodunun tek tip bir
    nesne şekliyle çalışabilmesidir.
    """

    image_id: str
    matched_screen_id: Optional[str] = None
    matched_screen_name: Optional[str] = None
    screen_match_score: float = 0.0
    scene_title: str
    visible_ui_elements: List[str] = Field(default_factory=list)
    primary_target: str
    target_element_id: Optional[str] = None
    action_type: str
    instruction_text: str
    narration: str
    on_screen_text: str
    highlight_description: str
    highlight_rect: Optional[VisionHighlightRect] = None
    confidence: float
    requires_review: bool
    grounding_source_ids: List[str] = Field(default_factory=list)
    grounding_warnings: List[str] = Field(default_factory=list)

    @field_validator(
        "image_id", "scene_title", "primary_target", "instruction_text", "narration", "highlight_description"
    )
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

    @field_validator("visible_ui_elements", "grounding_source_ids", "grounding_warnings")
    @classmethod
    def must_be_list(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("Bu alan bir liste olmalı")
        return v

    @field_validator("action_type")
    @classmethod
    def valid_action_type(cls, v: str) -> str:
        if v not in ACTION_TYPES:
            raise ValueError(
                f"Geçersiz action_type: {v}. Geçerli değerler: {', '.join(sorted(ACTION_TYPES))}"
            )
        return v

    @field_validator("confidence", "screen_match_score")
    @classmethod
    def score_range(cls, v: float) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("Bu alan bir sayı olmalı")
        if not (0.0 <= v <= 1.0):
            raise ValueError("Bu alan 0 ile 1 arasında olmalı")
        return float(v)


def validate_grounded_scene_result(data: dict) -> GroundedSceneResult:
    """GroundedSceneResult şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return GroundedSceneResult.model_validate(data)
