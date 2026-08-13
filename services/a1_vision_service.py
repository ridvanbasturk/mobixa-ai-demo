"""A1 AI Görsel Analiz Modu için çok-modlu (multimodal) model çağrısı orkestrasyonu.

Streamlit'ten bağımsızdır (a2_chat_service.py ile aynı desen). Her ekran
görüntüsü BAĞIMSIZ olarak (bir istekte tek görsel) analiz edilir; ekran
görüntüsü baytları yalnızca bu modüldeki `call_model` çağrısına parametre
olarak geçer, hiçbir yerde loglanmaz veya CSV'ye yazılmaz.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from PIL import Image
from pydantic import ValidationError

from schemas.a1_knowledge_models import ProductKnowledgeBase
from schemas.a1_video_models import HighlightRect
from schemas.a1_vision_models import (
    GroundedSceneResult,
    VisionHighlightRect,
    VisionSceneResult,
    VisualObservation,
    validate_grounded_scene_result,
    validate_vision_scene_result,
    validate_visual_observation,
)
from services.a1_knowledge_service import (
    build_grounding_context,
    get_screen,
    get_workflow_step,
    match_screen,
    match_target_element,
)
from services.a1_vision_validation import validate_grounded_result, validate_vision_result
from services.a1_video_service import draw_highlight_rect
from services.bedrock_client import ModelCallResult, call_model

DEFAULT_SCENE_DURATION_SECONDS = 5

_MIME_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "JPG": "image/jpeg"}


def detect_image_mime_type(image_bytes: bytes) -> str:
    """Görsel baytlarından MIME türünü algılar; belirlenemezse PNG varsayılır."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return _MIME_TYPES.get((img.format or "").upper(), "image/png")
    except Exception:  # noqa: BLE001
        return "image/png"


def build_vision_user_prompt(
    image_id: str,
    order: int,
    scene_label: Optional[str],
    user_note: Optional[str],
    overall_goal: Optional[str],
    target_audience: str,
    tone: str,
    neighbor_context: Optional[str] = None,
) -> str:
    """Modele yalnızca metin bağlamı gönderir; görsel ayrı olarak (data URL) eklenir."""
    context = {
        "image_id": image_id,
        "order": order,
        "scene_label": scene_label or None,
        "user_note": user_note or None,
        "overall_goal": overall_goal or None,
        "target_audience": target_audience,
        "tone": tone,
        "neighbor_context": neighbor_context or None,
    }
    return (
        "SAHNE BAĞLAMI:\n---\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n---\n\nYukarıdaki bağlamı ve ekli ekran görüntüsünü kullanarak, "
        "kurallara tam olarak uyan bir görsel analiz JSON'u üret."
    )


@dataclass
class VisionAnalysisOutcome:
    call_result: ModelCallResult
    json_valid: bool
    schema_valid: bool
    schema_error: Optional[str]
    validated: Optional[VisionSceneResult]
    business_result: Optional[Dict]


def run_vision_analysis(
    model_id: str,
    system_prompt: str,
    image_bytes: bytes,
    image_id: str,
    order: int,
    scene_label: Optional[str],
    user_note: Optional[str],
    overall_goal: Optional[str],
    target_audience: str,
    tone: str,
    temperature: float,
    max_tokens: int,
    neighbor_context: Optional[str] = None,
) -> VisionAnalysisOutcome:
    """Tek bir ekran görüntüsü için tek bir modelle görsel analiz çalıştırır ve doğrular."""
    user_prompt = build_vision_user_prompt(
        image_id, order, scene_label, user_note, overall_goal, target_audience, tone, neighbor_context
    )
    image_mime_type = detect_image_mime_type(image_bytes)
    call_result = call_model(
        model_id,
        system_prompt,
        user_prompt,
        temperature,
        max_tokens,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
    )

    schema_valid = False
    schema_error = None
    validated = None

    if call_result.success and call_result.parsed_json is not None:
        try:
            validated = validate_vision_scene_result(call_result.parsed_json)
            schema_valid = True
        except (ValidationError, ValueError) as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)

    json_valid = call_result.parsed_json is not None

    business_result = None
    if validated is not None:
        business_result = validate_vision_result(validated, image_id)

    return VisionAnalysisOutcome(
        call_result=call_result,
        json_valid=json_valid,
        schema_valid=schema_valid,
        schema_error=schema_error,
        validated=validated,
        business_result=business_result,
    )


# --- Faz 4B: iki aşamalı, bilgi tabanına bağlı (grounded) analiz -------------


def build_observation_user_prompt(
    image_id: str,
    order: int,
    scene_label: Optional[str],
    neighbor_context: Optional[str] = None,
) -> str:
    """Aşama 1 (görsel gözlem) için modele yalnızca metin bağlamı gönderir."""
    context = {
        "image_id": image_id,
        "order": order,
        "scene_label": scene_label or None,
        "neighbor_context": neighbor_context or None,
    }
    return (
        "SAHNE BAĞLAMI:\n---\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n---\n\nYalnızca ekli ekran görüntüsünde gerçekten görünen öğeleri "
        "açıklayan bir görsel gözlem JSON'u üret. Ürün davranışını açıklama."
    )


def build_grounded_user_prompt(
    observation: VisualObservation,
    screen_match: Optional[Dict],
    target_match: Optional[Dict],
    grounding_context: Optional[Dict],
    workflow_id: Optional[str],
    expected_order: Optional[int],
    overall_goal: Optional[str],
    target_audience: str,
    tone: str,
    user_note: Optional[str],
) -> str:
    """Aşama 2 (grounded sahne üretimi) için modele gözlem + deterministik eşleştirme + bilgi tabanı bağlamını gönderir."""
    payload = {
        "visual_observation": observation.model_dump(),
        "screen_match": screen_match,
        "target_match": target_match,
        "grounding_context": grounding_context,
        "workflow_id": workflow_id,
        "expected_step_order": expected_order,
        "overall_goal": overall_goal or None,
        "target_audience": target_audience,
        "tone": tone,
        "user_note": user_note or None,
    }
    return (
        "GROUNDING VERİSİ:\n---\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n---\n\nYukarıdaki görsel gözlemi ve (varsa) onaylı bilgi tabanı "
        "bağlamını kullanarak, kurallara tam olarak uyan bir grounded sahne "
        "JSON'u üret."
    )


def compute_grounding_source_ids(
    screen_match: Optional[Dict],
    target_match: Optional[Dict],
    workflow_id: Optional[str],
    expected_order: Optional[int],
) -> List[str]:
    """grounding_source_ids'i modelin serbest metninden değil, deterministik
    eşleştirme sonuçlarından hesaplar (bilgi tabanı gerçeklerinin modelce
    sessizce değiştirilmesini önler)."""
    source_ids: List[str] = []
    if screen_match and screen_match.get("matched_screen_id"):
        source_ids.append(f"screen:{screen_match['matched_screen_id']}")
    if target_match and target_match.get("target_element_id"):
        source_ids.append(f"element:{target_match['target_element_id']}")
    if workflow_id and expected_order is not None:
        source_ids.append(f"workflow:{workflow_id}:step:{expected_order}")
    return source_ids


@dataclass
class GroundedVisionOutcome:
    observation_call_result: ModelCallResult
    observation_json_valid: bool
    observation_schema_valid: bool
    observation_schema_error: Optional[str]
    observation: Optional[VisualObservation]
    screen_match: Optional[Dict]
    target_match: Optional[Dict]
    grounding_context: Optional[Dict]
    grounded_call_result: Optional[ModelCallResult]
    grounded_json_valid: bool
    grounded_schema_valid: bool
    grounded_schema_error: Optional[str]
    grounded: Optional[GroundedSceneResult]
    business_result: Optional[Dict]


def run_grounded_vision_analysis(
    model_id: str,
    observation_system_prompt: str,
    grounded_system_prompt: str,
    image_bytes: bytes,
    image_id: str,
    order: int,
    scene_label: Optional[str],
    user_note: Optional[str],
    overall_goal: Optional[str],
    target_audience: str,
    tone: str,
    kb: ProductKnowledgeBase,
    temperature: float,
    max_tokens: int,
    workflow_id: Optional[str] = None,
    expected_order: Optional[int] = None,
    neighbor_context: Optional[str] = None,
) -> GroundedVisionOutcome:
    """Tek bir ekran görüntüsü için iki aşamalı, bilgi tabanına bağlı analiz çalıştırır.

    Aşama 1: yalnızca görsel gözlem (ürün davranışı yorumu yok).
    Aşama 2: gözlem + deterministik ekran/hedef eşleştirmesi + onaylı bilgi
    tabanı bağlamından nihai (grounded) sahne üretimi. matched_screen_id/
    target_element_id/grounding_source_ids alanları modelin çıktısından
    BAĞIMSIZ olarak deterministik eşleştirme sonuçlarıyla üzerine yazılır.
    """
    image_mime_type = detect_image_mime_type(image_bytes)

    # --- Aşama 1: Görsel gözlem ---
    observation_user_prompt = build_observation_user_prompt(image_id, order, scene_label, neighbor_context)
    observation_call_result = call_model(
        model_id,
        observation_system_prompt,
        observation_user_prompt,
        temperature,
        max_tokens,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
    )

    observation_schema_valid = False
    observation_schema_error = None
    observation: Optional[VisualObservation] = None
    if observation_call_result.success and observation_call_result.parsed_json is not None:
        try:
            observation = validate_visual_observation(observation_call_result.parsed_json)
            observation_schema_valid = True
        except (ValidationError, ValueError) as exc:
            observation_schema_error = "Pydantic doğrulama hatası:\n" + str(exc)
    observation_json_valid = observation_call_result.parsed_json is not None

    screen_match: Optional[Dict] = None
    target_match: Optional[Dict] = None
    grounding_context: Optional[Dict] = None
    grounded_call_result: Optional[ModelCallResult] = None
    grounded_json_valid = False
    grounded_schema_valid = False
    grounded_schema_error: Optional[str] = None
    grounded: Optional[GroundedSceneResult] = None
    business_result: Optional[Dict] = None

    if observation is not None:
        # --- Deterministik ekran eşleştirmesi (Faz 4A) ---
        detected_labels = observation.detected_visible_labels or observation.visible_ui_elements
        screen_match = match_screen(kb, detected_labels, workflow_id=workflow_id, expected_order=expected_order)

        expected_screen_id = None
        if workflow_id and expected_order is not None:
            step = get_workflow_step(kb, workflow_id, expected_order)
            if step is not None:
                expected_screen_id = step.screen_id

        matched_screen_id = screen_match.get("matched_screen_id")
        if matched_screen_id:
            grounding_context = build_grounding_context(
                kb, matched_screen_id, workflow_id=workflow_id, step_order=expected_order
            )
            target_match = match_target_element(kb, matched_screen_id, observation.possible_primary_target)

        # --- Aşama 2: Grounded sahne üretimi ---
        grounded_user_prompt = build_grounded_user_prompt(
            observation,
            screen_match,
            target_match,
            grounding_context,
            workflow_id,
            expected_order,
            overall_goal,
            target_audience,
            tone,
            user_note,
        )
        grounded_call_result = call_model(
            model_id,
            grounded_system_prompt,
            grounded_user_prompt,
            temperature,
            max_tokens,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )

        if grounded_call_result.success and grounded_call_result.parsed_json is not None:
            try:
                grounded = validate_grounded_scene_result(grounded_call_result.parsed_json)
                grounded_schema_valid = True
            except (ValidationError, ValueError) as exc:
                grounded_schema_error = "Pydantic doğrulama hatası:\n" + str(exc)
        grounded_json_valid = grounded_call_result.parsed_json is not None

        if grounded is not None:
            # Bilgi tabanı gerçekleri modelin serbest metnine bırakılmaz:
            # deterministik eşleştirme sonuçlarıyla üzerine yazılır.
            matched_screen = get_screen(kb, matched_screen_id) if matched_screen_id else None
            grounded.matched_screen_id = matched_screen_id
            grounded.matched_screen_name = matched_screen.screen_name if matched_screen else None
            grounded.screen_match_score = screen_match.get("score", 0.0) if screen_match else 0.0
            grounded.target_element_id = target_match.get("target_element_id") if target_match else None
            grounded.grounding_source_ids = compute_grounding_source_ids(
                screen_match, target_match, workflow_id, expected_order
            )
            # Faz 4'ün genel kuralı: AI tarafından üretilen her görsel analiz
            # sonucu, bilgi tabanına bağlı olsa bile gözden geçirme gerektirir.
            grounded.requires_review = True

            business_result = validate_grounded_result(
                grounded, image_id, kb, observation=observation, expected_screen_id=expected_screen_id
            )
            # validate_grounded_result, eşleşme yoksa "Ekran bilgi tabanıyla
            # güvenilir biçimde eşleştirilemedi." uyarısını zaten ekler; tek
            # kaynak olarak business_result["warnings"] kullanılır.
            grounded.grounding_warnings = list(business_result["warnings"])

    return GroundedVisionOutcome(
        observation_call_result=observation_call_result,
        observation_json_valid=observation_json_valid,
        observation_schema_valid=observation_schema_valid,
        observation_schema_error=observation_schema_error,
        observation=observation,
        screen_match=screen_match,
        target_match=target_match,
        grounding_context=grounding_context,
        grounded_call_result=grounded_call_result,
        grounded_json_valid=grounded_json_valid,
        grounded_schema_valid=grounded_schema_valid,
        grounded_schema_error=grounded_schema_error,
        grounded=grounded,
        business_result=business_result,
    )


def grounded_result_to_storyboard_scene(
    grounded: GroundedSceneResult,
    scene_number: int,
    duration_seconds: int = DEFAULT_SCENE_DURATION_SECONDS,
    transition: str = "cut",
) -> Dict:
    """GroundedSceneResult'ı storyboard sahne sözlük formatına dönüştürür.

    vision_result_to_storyboard_scene ile aynı temel alanlara ek olarak
    grounding meta verisini (matched_screen_id, target_element_id,
    grounding_source_ids, grounding_warnings) korur. Yeni alanların tümü
    isteğe bağlıdır; mevcut Storyboard Pydantic şeması bunları yok sayar
    (geriye dönük uyumlu).
    """
    return {
        "scene_number": scene_number,
        "image_id": grounded.image_id,
        "scene_title": grounded.scene_title,
        "duration_seconds": duration_seconds,
        "narration": grounded.narration,
        "on_screen_text": grounded.on_screen_text,
        "transition": transition,
        "zoom_enabled": True,
        "highlight_description": grounded.highlight_description,
        "requires_review": True,
        "highlight_rect": grounded.highlight_rect.model_dump() if grounded.highlight_rect else None,
        "action_type": grounded.action_type,
        "target_label": grounded.primary_target,
        "instruction_text": grounded.instruction_text,
        "cursor_enabled": grounded.action_type in {"click", "select", "enter_text"},
        "click_effect_enabled": grounded.action_type == "click",
        "matched_screen_id": grounded.matched_screen_id,
        "target_element_id": grounded.target_element_id,
        "grounding_source_ids": list(grounded.grounding_source_ids),
        "grounding_warnings": list(grounded.grounding_warnings),
    }


def build_highlight_preview(image_bytes: bytes, rect: Optional[VisionHighlightRect]) -> bytes:
    """Vurgu dikdörtgeni varsa ekran görüntüsü üzerine çizilmiş bir önizleme üretir.

    Koordinat yoksa (highlight_rect=None) orijinal görsel baytları değişmeden
    döner — hiçbir koordinat uydurulmaz.
    """
    if rect is None:
        return image_bytes
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        video_rect = HighlightRect(x=rect.x, y=rect.y, width=rect.width, height=rect.height)
        annotated = draw_highlight_rect(img, video_rect)
        buf = io.BytesIO()
        annotated.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()


def vision_result_to_storyboard_scene(
    vision: VisionSceneResult,
    scene_number: int,
    duration_seconds: int = DEFAULT_SCENE_DURATION_SECONDS,
    transition: str = "cut",
) -> Dict:
    """VisionSceneResult'ı mevcut A1 storyboard sahne sözlük formatına dönüştürür.

    highlight_rect/action_type/target_label/instruction_text/cursor_enabled/
    click_effect_enabled alanları eklenir; mevcut Storyboard Pydantic şeması
    (schemas/a1_storyboard_models.py) bilinmeyen alanları yok sayar
    (extra="ignore" varsayılanı) — bu yüzden şemaya dokunulmadan mevcut
    doğrulama/düzenleme akışı olduğu gibi çalışmaya devam eder; bu ek
    alanlar yalnızca video render katmanı tarafından kullanılır.
    """
    return {
        "scene_number": scene_number,
        "image_id": vision.image_id,
        "scene_title": vision.scene_title,
        "duration_seconds": duration_seconds,
        "narration": vision.narration,
        "on_screen_text": vision.on_screen_text,
        "transition": transition,
        "zoom_enabled": True,
        "highlight_description": vision.highlight_description,
        "requires_review": True,
        "highlight_rect": vision.highlight_rect.model_dump() if vision.highlight_rect else None,
        "action_type": vision.action_type,
        "target_label": vision.primary_target,
        "instruction_text": vision.instruction_text,
        "cursor_enabled": vision.action_type in {"click", "select", "enter_text"},
        "click_effect_enabled": vision.action_type == "click",
    }


def build_vision_storyboard(
    title: str,
    target_audience: str,
    tone: str,
    selected_scenes: List[Dict],
    closing_text: str = "Bu adımları takip ederek işlemi tamamlayabilirsiniz.",
) -> Dict:
    """Sıralı, seçilmiş vision sahnelerinden tam bir storyboard sözlüğü oluşturur."""
    total_duration = sum(int(s["duration_seconds"]) for s in selected_scenes)
    return {
        "title": title,
        "target_audience": target_audience,
        "tone": tone,
        "scenes": selected_scenes,
        "total_duration_seconds": total_duration,
        "closing_text": closing_text,
    }
