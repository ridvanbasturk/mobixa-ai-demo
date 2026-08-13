"""A2 için model çağrısı orkestrasyonu.

Streamlit'ten bağımsızdır (Streamlit içermez, session_state kullanmaz);
bu sayede AWS'ye gerçek çağrı yapılmadan test edilebilir. `call_model`
Bedrock'a gerçek bir istek gönderir; bu modülün geri kalanı saf Python'dur.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import ValidationError

from schemas.a2_models import A2Output, validate_a2_output
from services.a2_validation import compute_final_escalation, validate_grounding
from services.bedrock_client import ModelCallResult, call_model
from services.i18n_strings.a2 import EN as _A2_EN, TR as _A2_TR

_LABELS = {"tr": _A2_TR, "en": _A2_EN}


def build_user_prompt(question: str, retrieved_entries: List[Dict], language: str = "tr") -> str:
    labels = _LABELS.get(language, _A2_TR)
    if retrieved_entries:
        context_payload = [
            {
                "id": e["id"],
                "title": e["title"],
                "content": e["content"],
                "product_area": e.get("product_area", ""),
            }
            for e in retrieved_entries
        ]
        context_block = json.dumps(context_payload, ensure_ascii=False, indent=2)
    else:
        context_block = labels["a2.user_prompt.no_context"]

    return f"""{labels["a2.user_prompt.question_label"]}
{question}

{labels["a2.user_prompt.context_label"]}
{context_block}
"""


@dataclass
class ChatTurnResult:
    call_result: ModelCallResult
    json_valid: bool
    schema_valid: bool
    schema_error: Optional[str]
    validated: Optional[A2Output]
    grounding_result: Optional[Dict]
    model_escalation_recommended: Optional[bool]
    final_needs_escalation: bool


def run_chat_turn(
    model_id: str,
    system_prompt: str,
    question: str,
    retrieved_entries: List[Dict],
    retrieval_sufficient: bool,
    temperature: float,
    max_tokens: int,
    language: str = "tr",
) -> ChatTurnResult:
    """Tek bir modelle tek bir soru-cevap turu çalıştırır ve doğrular."""
    user_prompt = build_user_prompt(question, retrieved_entries, language)
    call_result = call_model(model_id, system_prompt, user_prompt, temperature, max_tokens)

    schema_valid = False
    schema_error = None
    validated = None

    if call_result.success and call_result.parsed_json is not None:
        try:
            validated = validate_a2_output(call_result.parsed_json)
            schema_valid = True
        except (ValidationError, ValueError) as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)

    json_valid = call_result.parsed_json is not None

    grounding_result = None
    model_escalation_recommended = None
    if validated is not None:
        model_escalation_recommended = validated.escalation_recommended
        grounding_result = validate_grounding(validated.answer, validated.source_ids, retrieved_entries)

    final_needs_escalation = compute_final_escalation(
        retrieved_entries=retrieved_entries,
        retrieval_sufficient=retrieval_sufficient,
        model_escalation_recommended=bool(model_escalation_recommended),
        grounding_result=grounding_result,
    )

    return ChatTurnResult(
        call_result=call_result,
        json_valid=json_valid,
        schema_valid=schema_valid,
        schema_error=schema_error,
        validated=validated,
        grounding_result=grounding_result,
        model_escalation_recommended=model_escalation_recommended,
        final_needs_escalation=final_needs_escalation,
    )
