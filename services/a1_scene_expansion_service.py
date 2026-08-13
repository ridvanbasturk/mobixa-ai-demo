"""A1 Faz 4C — grounded ekran sonucunun birden fazla öğretici alt sahneye
(sub-scene) genişletilmesi için model çağrısı orkestrasyonu.

Streamlit'ten bağımsızdır (a1_vision_service.py ile aynı desen). Ekran
görüntüsü baytları bu aşamada modele TEKRAR GÖNDERİLMEZ: Aşama 2'nin
(grounded) ürettiği görsel gözlem + onaylı bilgi tabanı bağlamı, alt sahne
üretimi için yeterli metin bağlamını zaten sağlar; bu, gereksiz ek ücretli
model çağrısını (görsel + metin yerine yalnızca metin) önler.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import ValidationError

from schemas.a1_knowledge_models import ProductKnowledgeBase
from schemas.a1_scene_expansion_models import SceneExpansionResult, SubScene, validate_scene_expansion_result
from schemas.a1_vision_models import GroundedSceneResult
from services.a1_duration_service import DURATION_SOURCE, estimate_recommended_duration
from services.a1_vision_validation import validate_scene_expansion
from services.bedrock_client import ModelCallResult, call_model

DEFAULT_TRANSITION = "cut"


def build_expansion_user_prompt(
    grounded: GroundedSceneResult,
    kb: ProductKnowledgeBase,
    grounding_context: Optional[Dict],
    workflow_id: Optional[str],
    expected_order: Optional[int],
    title: str,
    target_audience: str,
    tone: str,
    user_note: Optional[str],
) -> str:
    """Modele yalnızca grounded sonucu + bilgi tabanı bağlamını (metin) gönderir."""
    approved_elements = [
        {
            "element_id": e.element_id,
            "visible_label": e.visible_label,
            "element_type": e.element_type,
            "purpose": e.purpose,
            "action_type": e.action_type,
        }
        for e in kb.ui_elements
        if e.screen_id == grounded.matched_screen_id
    ]
    payload = {
        "image_id": grounded.image_id,
        "matched_screen_id": grounded.matched_screen_id,
        "matched_screen_name": grounded.matched_screen_name,
        "current_grounded_scene": {
            "scene_title": grounded.scene_title,
            "primary_target": grounded.primary_target,
            "action_type": grounded.action_type,
            "instruction_text": grounded.instruction_text,
            "narration": grounded.narration,
        },
        "approved_ui_elements": approved_elements,
        "grounding_context": grounding_context,
        "workflow_id": workflow_id,
        "expected_step_order": expected_order,
        "video_title": title,
        "target_audience": target_audience,
        "tone": tone,
        "user_note": user_note or None,
    }
    return (
        "EKRAN GENİŞLETME VERİSİ:\n---\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n---\n\nYukarıdaki onaylı bilgileri kullanarak, kurallara tam olarak uyan "
        "bir alt sahne (sub_scenes) JSON'u üret."
    )


@dataclass
class SceneExpansionOutcome:
    call_result: ModelCallResult
    json_valid: bool
    schema_valid: bool
    schema_error: Optional[str]
    parsed: Optional[SceneExpansionResult]
    business_result: Optional[Dict]


def run_scene_expansion(
    model_id: str,
    system_prompt: str,
    grounded: GroundedSceneResult,
    kb: ProductKnowledgeBase,
    grounding_context: Optional[Dict],
    workflow_id: Optional[str],
    expected_order: Optional[int],
    title: str,
    target_audience: str,
    tone: str,
    user_note: Optional[str],
    temperature: float,
    max_tokens: int,
) -> SceneExpansionOutcome:
    """Tek bir eşleşmiş ekranı bir veya daha fazla alt sahneye genişletir ve doğrular."""
    user_prompt = build_expansion_user_prompt(
        grounded, kb, grounding_context, workflow_id, expected_order, title, target_audience, tone, user_note
    )
    call_result = call_model(model_id, system_prompt, user_prompt, temperature, max_tokens)

    schema_valid = False
    schema_error = None
    parsed: Optional[SceneExpansionResult] = None
    if call_result.success and call_result.parsed_json is not None:
        try:
            parsed = validate_scene_expansion_result(call_result.parsed_json)
            schema_valid = True
        except (ValidationError, ValueError) as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)

    json_valid = call_result.parsed_json is not None

    business_result = None
    if parsed is not None:
        # Faz 4'ün genel kuralı: AI tarafından üretilen her sahne, bilgi
        # tabanına bağlı olsa bile gözden geçirme gerektirir.
        for sub_scene in parsed.sub_scenes:
            sub_scene.requires_review = True
        business_result = validate_scene_expansion(parsed, grounded.matched_screen_id, kb)

    return SceneExpansionOutcome(
        call_result=call_result,
        json_valid=json_valid,
        schema_valid=schema_valid,
        schema_error=schema_error,
        parsed=parsed,
        business_result=business_result,
    )


def _warnings_for_sub_scene(business_result: Optional[Dict], sub_scene_key: str) -> List[str]:
    if not business_result:
        return []
    prefix = f"{sub_scene_key}: "
    return [w[len(prefix):] if w.startswith(prefix) else w for w in business_result["warnings"] if w.startswith(prefix)]


def expand_grounded_scene_to_storyboard_scenes(
    image_id: str,
    sub_scenes: List[SubScene],
    matched_screen_id: Optional[str],
    base_scene_number: int,
    business_result: Optional[Dict] = None,
    transition: str = DEFAULT_TRANSITION,
) -> List[Dict]:
    """Alt sahneleri, storyboard sahne sözlük formatına (Faz 4B'nin
    grounded_result_to_storyboard_scene'iyle aynı temel alanlar + scene_id +
    recommended_duration_seconds) dönüştürür.

    scene_number değerleri burada yalnızca BAŞLANGIÇ değeridir; storyboard'a
    aktarım sırasında tüm sahneler global olarak yeniden numaralandırılır
    (services/a1_storyboard_service.py::_renumber_scenes).
    """
    scenes: List[Dict] = []
    for idx, sub_scene in enumerate(sub_scenes, start=1):
        recommended_duration = estimate_recommended_duration(sub_scene.narration, sub_scene.action_type)
        scenes.append(
            {
                "scene_id": f"{image_id}_step_{idx:02d}",
                "scene_number": base_scene_number + idx - 1,
                "image_id": image_id,
                "scene_title": sub_scene.scene_title,
                "duration_seconds": recommended_duration,
                "recommended_duration_seconds": recommended_duration,
                "duration_source": DURATION_SOURCE,
                "narration": sub_scene.narration,
                "on_screen_text": sub_scene.on_screen_text,
                "transition": transition,
                "zoom_enabled": True,
                "highlight_description": sub_scene.highlight_description,
                "requires_review": True,
                "highlight_rect": sub_scene.highlight_rect.model_dump() if sub_scene.highlight_rect else None,
                "action_type": sub_scene.action_type,
                "target_label": sub_scene.scene_title,
                "instruction_text": sub_scene.instruction_text,
                "cursor_enabled": sub_scene.cursor_enabled,
                "click_effect_enabled": sub_scene.click_effect_enabled,
                "matched_screen_id": matched_screen_id,
                "target_element_id": sub_scene.target_element_id,
                "grounding_source_ids": list(sub_scene.grounding_source_ids),
                "grounding_warnings": _warnings_for_sub_scene(business_result, sub_scene.sub_scene_key),
            }
        )
    return scenes
