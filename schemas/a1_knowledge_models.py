"""A1 Ürün Bilgi Tabanı (screens/ui_elements/workflows/terminology) için Pydantic şemaları.

Bu şema, yerel JSON dosyalarından yüklenen bilgi tabanı kayıtlarının
birbirleriyle tutarlı olduğunu (referans bütünlüğü, benzersiz kimlikler,
ardışık iş akışı sırası) doğrular. "approved" olmayan (ör. "draft",
"deprecated") kayıtlar burada REDDEDİLMEZ — dosyada durabilirler; yalnızca
`services/a1_knowledge_service.py` içindeki retrieval (getirme) katmanı
tarafından dışlanır.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ELEMENT_TYPES = {
    "button",
    "input",
    "tab",
    "selector",
    "table",
    "menu",
    "information",
    "checkbox",
    "date_field",
}
ACTION_TYPES = {"click", "enter_text", "select", "review", "information"}
RECORD_STATUSES = {"approved", "draft", "deprecated"}
APPROVED_STATUS = "approved"


class KnowledgeScreen(BaseModel):
    screen_id: str
    screen_name: str
    product_area: str
    purpose: str
    visible_labels: List[str] = Field(default_factory=list)
    supported_roles: List[str] = Field(default_factory=list)
    workflow_ids: List[str] = Field(default_factory=list)
    product_version: str
    status: str
    last_updated: str

    @field_validator("screen_id", "screen_name", "product_area", "purpose", "product_version", "last_updated")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in RECORD_STATUSES:
            raise ValueError(f"Geçersiz durum: {v}. Geçerli değerler: {', '.join(sorted(RECORD_STATUSES))}")
        return v

    @model_validator(mode="after")
    def check_unique_labels(self) -> "KnowledgeScreen":
        if len(self.visible_labels) != len(set(self.visible_labels)):
            raise ValueError(f"{self.screen_id}: visible_labels içinde tekrarlanan etiket var")
        return self


class KnowledgeUIElement(BaseModel):
    element_id: str
    screen_id: str
    visible_label: str
    element_type: str
    purpose: str
    action_type: str
    result_screen_id: Optional[str] = None
    prerequisites: List[str] = Field(default_factory=list)
    notes: str = ""
    product_version: str
    status: str

    @field_validator("element_id", "screen_id", "visible_label", "purpose", "product_version")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("element_type")
    @classmethod
    def valid_element_type(cls, v: str) -> str:
        if v not in ELEMENT_TYPES:
            raise ValueError(f"Geçersiz element_type: {v}. Geçerli değerler: {', '.join(sorted(ELEMENT_TYPES))}")
        return v

    @field_validator("action_type")
    @classmethod
    def valid_action_type(cls, v: str) -> str:
        if v not in ACTION_TYPES:
            raise ValueError(f"Geçersiz action_type: {v}. Geçerli değerler: {', '.join(sorted(ACTION_TYPES))}")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in RECORD_STATUSES:
            raise ValueError(f"Geçersiz durum: {v}. Geçerli değerler: {', '.join(sorted(RECORD_STATUSES))}")
        return v


class WorkflowStep(BaseModel):
    step_id: str
    order: int
    screen_id: str
    target_element_id: str
    instruction: str
    expected_next_screen_id: Optional[str] = None

    @field_validator("step_id", "screen_id", "target_element_id", "instruction")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("order")
    @classmethod
    def positive_order(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("order pozitif olmalı")
        return v


class KnowledgeWorkflow(BaseModel):
    workflow_id: str
    title: str
    purpose: str
    supported_roles: List[str] = Field(default_factory=list)
    product_version: str
    status: str
    steps: List[WorkflowStep]

    @field_validator("workflow_id", "title", "purpose", "product_version")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Alan boş olamaz")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in RECORD_STATUSES:
            raise ValueError(f"Geçersiz durum: {v}. Geçerli değerler: {', '.join(sorted(RECORD_STATUSES))}")
        return v

    @model_validator(mode="after")
    def check_steps(self) -> "KnowledgeWorkflow":
        if not self.steps:
            raise ValueError(f"{self.workflow_id}: en az bir adım olmalı")

        step_ids = [s.step_id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError(f"{self.workflow_id}: step_id değerleri benzersiz olmalı")

        orders = sorted(s.order for s in self.steps)
        if len(orders) != len(set(orders)):
            raise ValueError(f"{self.workflow_id}: order değerleri benzersiz olmalı")
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError(f"{self.workflow_id}: adım sırası 1'den başlayarak ardışık olmalı")

        return self


class TerminologyEntry(BaseModel):
    canonical: str
    alternatives: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)

    @field_validator("canonical")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("canonical boş olamaz")
        return v


class ProductKnowledgeBase(BaseModel):
    screens: List[KnowledgeScreen]
    ui_elements: List[KnowledgeUIElement]
    workflows: List[KnowledgeWorkflow]
    terminology: List[TerminologyEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_cross_references(self) -> "ProductKnowledgeBase":
        screen_ids = [s.screen_id for s in self.screens]
        if len(screen_ids) != len(set(screen_ids)):
            raise ValueError("screen_id değerleri benzersiz olmalı")
        screen_id_set = set(screen_ids)

        element_ids = [e.element_id for e in self.ui_elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("element_id değerleri benzersiz olmalı")
        element_id_set = set(element_ids)

        workflow_ids = [w.workflow_id for w in self.workflows]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("workflow_id değerleri benzersiz olmalı")
        workflow_id_set = set(workflow_ids)

        all_step_ids = [s.step_id for w in self.workflows for s in w.steps]
        if len(all_step_ids) != len(set(all_step_ids)):
            raise ValueError("step_id değerleri tüm iş akışlarında benzersiz olmalı")

        for element in self.ui_elements:
            if element.screen_id not in screen_id_set:
                raise ValueError(f"{element.element_id}: screen_id '{element.screen_id}' bulunamadı")
            if element.result_screen_id is not None and element.result_screen_id not in screen_id_set:
                raise ValueError(
                    f"{element.element_id}: result_screen_id '{element.result_screen_id}' bulunamadı"
                )

        for workflow in self.workflows:
            for step in workflow.steps:
                if step.screen_id not in screen_id_set:
                    raise ValueError(
                        f"{workflow.workflow_id}/{step.step_id}: screen_id '{step.screen_id}' bulunamadı"
                    )
                if step.target_element_id not in element_id_set:
                    raise ValueError(
                        f"{workflow.workflow_id}/{step.step_id}: target_element_id "
                        f"'{step.target_element_id}' bulunamadı"
                    )
                if step.expected_next_screen_id is not None and step.expected_next_screen_id not in screen_id_set:
                    raise ValueError(
                        f"{workflow.workflow_id}/{step.step_id}: expected_next_screen_id "
                        f"'{step.expected_next_screen_id}' bulunamadı"
                    )

        for screen in self.screens:
            for wf_id in screen.workflow_ids:
                if wf_id not in workflow_id_set:
                    raise ValueError(f"{screen.screen_id}: workflow_ids içindeki '{wf_id}' bulunamadı")

        return self


def validate_knowledge_base(data: dict) -> ProductKnowledgeBase:
    """ProductKnowledgeBase şemasına göre doğrular. Hata durumunda ValidationError fırlatır."""
    return ProductKnowledgeBase.model_validate(data)
