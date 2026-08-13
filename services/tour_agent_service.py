"""Tur ajanının karar katmanı — Streamlit ve Playwright'tan BAĞIMSIZ.

Bu modül tarayıcıyı sürmez; yalnızca "şu anda ekran böyle görünüyor, sıradaki
adım ne olmalı" sorusunu modele sorar ve cevabı doğrular. Tarayıcı işleri
`services/tour_pipeline.py` içindedir. Bu ayrım sayesinde ajanın karar mantığı
tarayıcı açmadan, sahte bir `call_model` ile test edilebilir.

Set-of-Mark: modele gönderilen ekran görüntüsü, envanterdeki numaralarla
eşleşen rozetlerle işaretlenir. Rozetler yalnızca GÖRÜNTÜNÜN KOPYASINA
basılır — kaydedilen videoya asla girmez.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from pydantic import ValidationError

from schemas.tour_models import TourElement, TourStepDecision, validate_tour_decision
from services.tour_dom_inspector import format_inventory_for_model
from services.tour_validation import decision_signature, validate_decision_against_inventory

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Rozet görünümü (Set-of-Mark). Kontrast, modelin rozetleri arayüzün kendi
# renklerinden ayırt edebilmesi için yüksek tutulur.
BADGE_FILL = (255, 60, 0)
BADGE_TEXT = (255, 255, 255)
BADGE_HEIGHT = 20


def load_agent_system_prompt(language: str) -> str:
    filename = "tour_agent_system_en.txt" if language == "en" else "tour_agent_system.txt"
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def annotate_screenshot(image_bytes: bytes, inventory: List[TourElement]) -> bytes:
    """Ekran görüntüsünün KOPYASINA numaralı rozetler basar.

    Pillow yoksa (veya görüntü açılamazsa) orijinal baytları olduğu gibi döner —
    ajan yine envanter metnini görür, yalnızca görsel ipucu olmaz.
    """
    try:
        from PIL import Image, ImageDraw  # noqa: PLC0415 - isteğe bağlı bağımlılık
    except ImportError:
        return image_bytes

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:  # noqa: BLE001 - bozuk görüntü ajanı durdurmamalı
        return image_bytes

    draw = ImageDraw.Draw(image)
    for element in inventory:
        label = str(element.index)
        badge_width = 14 + 9 * len(label)
        left = max(0, min(element.x, image.width - badge_width))
        top = max(0, min(element.y, image.height - BADGE_HEIGHT))
        draw.rectangle(
            [left, top, left + badge_width, top + BADGE_HEIGHT],
            fill=BADGE_FILL,
        )
        draw.text((left + 6, top + 4), label, fill=BADGE_TEXT)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class AgentContext:
    """Ajanın tur boyunca taşıdığı durum."""

    module_title: str
    language: str
    max_steps: int
    history: List[str] = field(default_factory=list)
    signatures: List[str] = field(default_factory=list)
    # Bir önceki denemede doğrulamadan geçemeyen kararın hatası. Ajana geri
    # bildirilir ki aynı hatayı tekrarlamak yerine düzeltebilsin.
    last_error: Optional[str] = None

    def remember(
        self,
        decision: TourStepDecision,
        element: Optional[TourElement],
        signature: Optional[str] = None,
    ) -> None:
        target = f' → "{element.name}"' if element else ""
        self.history.append(f"{len(self.history) + 1}. {decision.action}{target}: {decision.narration}")
        # İmza doğrulama katmanından gelmelidir; orada öğe kimliğiyle (indeksle
        # DEĞİL) hesaplanır — bkz. services/tour_validation.py::decision_signature
        self.signatures.append(signature or decision_signature(decision, element))
        self.last_error = None

    def history_text(self) -> str:
        if not self.history:
            return "(Henüz adım atılmadı — bu turun ilk adımı.)"
        # Yalnızca son adımlar; prompt'u şişirmemek için sınırlı tutulur.
        return "\n".join(self.history[-8:])

    def error_text(self) -> str:
        """Önceki başarısız denemenin modele gösterilecek geri bildirimi."""
        if not self.last_error:
            return ""
        if self.language == "en":
            return (
                "\nYOUR PREVIOUS ATTEMPT WAS REJECTED:\n"
                f"{self.last_error}\n"
                "Fix this and return a valid decision. If you wanted to target an "
                "element, you must give an element_index from the list below.\n"
            )
        return (
            "\nBİR ÖNCEKİ DENEMEN REDDEDİLDİ:\n"
            f"{self.last_error}\n"
            "Bunu düzeltip geçerli bir karar ver. Bir öğeyi hedeflemek "
            "istiyorsan aşağıdaki listeden bir element_index vermelisin.\n"
        )


@dataclass
class AgentDecisionResult:
    """Tek bir karar turunun sonucu (model çağrısı + doğrulama)."""

    decision: Optional[TourStepDecision]
    element: Optional[TourElement]
    valid: bool
    errors: List[str]
    raw_text: Optional[str]
    call_success: bool
    call_error: Optional[str]
    latency_ms: Optional[float]
    estimated_cost_usd: Optional[float]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    signature: str = ""


def build_user_prompt(context: AgentContext, inventory: List[TourElement], step_index: int) -> str:
    """Modele gönderilecek kullanıcı mesajını kurar."""
    remaining = context.max_steps - step_index + 1
    if context.language == "en":
        return (
            f"MODULE BEING TOURED: {context.module_title}\n"
            f"STEP: {step_index} (at most {remaining} steps left)\n\n"
            f"WHAT YOU HAVE DONE SO FAR:\n{context.history_text()}\n"
            f"{context.error_text()}\n"
            f"INTERACTIVE ELEMENTS ON SCREEN RIGHT NOW:\n"
            f"{format_inventory_for_model(inventory)}\n\n"
            "Look at the screenshot and decide the single next step."
        )
    return (
        f"TURU ÇEKİLEN MODÜL: {context.module_title}\n"
        f"ADIM: {step_index} (en fazla {remaining} adım kaldı)\n\n"
        f"ŞİMDİYE KADAR YAPTIKLARIN:\n{context.history_text()}\n"
        f"{context.error_text()}\n"
        f"ŞU ANDA EKRANDAKİ ETKİLEŞİMLİ ÖĞELER:\n"
        f"{format_inventory_for_model(inventory)}\n\n"
        "Ekran görüntüsüne bak ve tek bir sonraki adıma karar ver."
    )


def decide_next_step(
    call_model: Callable,
    model_id: str,
    context: AgentContext,
    inventory: List[TourElement],
    screenshot_bytes: bytes,
    step_index: int,
    temperature: float = 0.3,
    max_tokens: int = 600,
) -> AgentDecisionResult:
    """Ekranın o anki hâline bakarak sıradaki adımı belirler.

    `call_model` dışarıdan verilir (varsayılan olarak
    `services.bedrock_client.call_model`) — böylece tarayıcı ve AWS olmadan
    test edilebilir.
    """
    system_prompt = load_agent_system_prompt(context.language)
    user_prompt = build_user_prompt(context, inventory, step_index)
    annotated = annotate_screenshot(screenshot_bytes, inventory)

    call_result = call_model(
        model_id,
        system_prompt,
        user_prompt,
        temperature,
        max_tokens,
        image_bytes=annotated,
        image_mime_type="image/png",
    )

    base = {
        "raw_text": call_result.raw_text,
        "call_success": call_result.api_call_success,
        "call_error": call_result.error,
        "latency_ms": call_result.latency_ms,
        "estimated_cost_usd": call_result.estimated_cost_usd,
        "input_tokens": call_result.input_tokens,
        "output_tokens": call_result.output_tokens,
        "total_tokens": call_result.total_tokens,
    }

    if call_result.parsed_json is None:
        return AgentDecisionResult(
            decision=None,
            element=None,
            valid=False,
            errors=[call_result.error or "Model yanıtı JSON olarak ayrıştırılamadı."],
            signature="",
            **base,
        )

    try:
        decision = validate_tour_decision(call_result.parsed_json)
    except (ValidationError, ValueError) as exc:
        return AgentDecisionResult(
            decision=None,
            element=None,
            valid=False,
            errors=[f"Karar şeması geçersiz: {exc}"],
            signature="",
            **base,
        )

    verdict = validate_decision_against_inventory(decision, inventory, context.signatures)
    return AgentDecisionResult(
        decision=decision,
        element=verdict["element"],
        valid=verdict["valid"],
        errors=verdict["errors"],
        signature=verdict["signature"],
        **base,
    )


def summarize_decision(decision: TourStepDecision, element: Optional[TourElement]) -> Dict:
    """Adım dökümü/JSON çıktısı için sadeleştirilmiş karar özeti."""
    return {
        "action": decision.action,
        "element_index": decision.element_index,
        "element_name": element.name if element else None,
        "text": decision.text,
        "narration": decision.narration,
        "reason": decision.reason,
    }


def dump_steps_json(steps: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(steps, ensure_ascii=False, indent=2), encoding="utf-8")
