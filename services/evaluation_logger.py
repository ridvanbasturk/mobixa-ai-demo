"""Model çağrısı sonuçlarını outputs/evaluations.csv dosyasına kaydeder.

Teknik ölçümler (log_evaluation) ile insan değerlendirmesi
(save_human_evaluation) aynı satırda run_id üzerinden eşleştirilir. Eski
sürümlerden kalan, yeni sütunları içermeyen bir CSV dosyası bulunursa,
dosya otomatik olarak yeni şemaya göç ettirilir (mevcut satırlar korunur,
eksik alanlar boş bırakılır).
"""
from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"
CSV_PATH = OUTPUTS_DIR / "evaluations.csv"

FIELDNAMES = [
    "timestamp",
    "run_id",
    "feature",
    "model_id",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "latency_ms",
    "estimated_cost_usd",
    "json_valid",
    "schema_valid",
    "question_count",
    "success",
    "error",
    "numeric_validation_passed",
    "numeric_validation_details",
    "human_answer_key_correct",
    "human_groundedness",
    "human_language_quality",
    "human_notes",
    "human_numeric_accuracy",
    "human_actionability",
    "human_causality_issue",
    "business_validation_passed",
    "business_validation_details",
    "weak_topics_covered",
    "weak_topics_total",
    "retrieved_source_ids",
    "cited_source_ids",
    "grounding_validation_passed",
    "grounding_validation_details",
    "model_escalation_recommended",
    "final_needs_escalation",
    # --- A1 tur ajanı (tarayıcıyı süren görsel ajan) --------------------------
    "tour_module",
    "tour_language",
    "tour_step_index",
    "tour_action",
    "tour_decision_valid",
    "tour_decision_error",
]


def _read_existing_header(csv_path: Path) -> Optional[list]:
    if not csv_path.exists():
        return None
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        try:
            return next(csv.reader(f))
        except StopIteration:
            return None


def _migrate_csv_if_needed(csv_path: Path = CSV_PATH) -> None:
    """Eski şemadaki bir CSV dosyasını yeni sütunlarla uyumlu hale getirir."""
    header = _read_existing_header(csv_path)
    if header is None or header == FIELDNAMES:
        return

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def log_evaluation(
    feature: str,
    model_id: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: Optional[int],
    latency_ms: Optional[float],
    estimated_cost_usd: Optional[float],
    json_valid: bool,
    schema_valid: bool,
    question_count: int,
    success: bool,
    error: Optional[str],
    run_id: Optional[str] = None,
    numeric_validation_passed: Optional[bool] = None,
    numeric_validation_details: Optional[str] = None,
    business_validation_passed: Optional[bool] = None,
    business_validation_details: Optional[str] = None,
    weak_topics_covered: Optional[int] = None,
    weak_topics_total: Optional[int] = None,
    retrieved_source_ids: Optional[str] = None,
    cited_source_ids: Optional[str] = None,
    grounding_validation_passed: Optional[bool] = None,
    grounding_validation_details: Optional[str] = None,
    model_escalation_recommended: Optional[bool] = None,
    final_needs_escalation: Optional[bool] = None,
    tour_module: Optional[str] = None,
    tour_language: Optional[str] = None,
    tour_step_index: Optional[int] = None,
    tour_action: Optional[str] = None,
    tour_decision_valid: Optional[bool] = None,
    tour_decision_error: Optional[str] = None,
    csv_path: Path = CSV_PATH,
) -> str:
    """Bir model çağrısının teknik ölçümlerini CSV'ye ekler.

    numeric_validation_* alanları yalnızca B6 gibi rakamsal doğrulama yapan
    özellikler tarafından kullanılır; business_validation_*/weak_topics_*
    alanları yalnızca C1 gibi deterministik iş kuralı doğrulaması yapan
    özellikler tarafından kullanılır; retrieved_source_ids/cited_source_ids/
    grounding_validation_*/*_escalation alanları yalnızca A2 gibi kaynak
    tabanlı (RAG benzeri) doğrulama yapan özellikler tarafından kullanılır;
    tour_* alanları yalnızca A1 tur ajanı tarafından kullanılır — ajanın her
    adımı ayrı bir satır olarak kaydedilir (ekran görüntüsü baytı veya tam
    prompt içeriği ASLA burada tutulmaz).
    Diğer özellikler için None bırakılır ve CSV'de boş yazılır.

    Döndürülen run_id, aynı satıra sonradan insan değerlendirmesi eklemek
    (save_human_evaluation) için kullanılır.
    """
    run_id = run_id or uuid.uuid4().hex

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _migrate_csv_if_needed(csv_path)
    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "feature": feature,
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
                "estimated_cost_usd": estimated_cost_usd,
                "json_valid": json_valid,
                "schema_valid": schema_valid,
                "question_count": question_count,
                "success": success,
                "error": error,
                "numeric_validation_passed": "" if numeric_validation_passed is None else numeric_validation_passed,
                "numeric_validation_details": numeric_validation_details or "",
                "human_answer_key_correct": "",
                "human_groundedness": "",
                "human_language_quality": "",
                "human_notes": "",
                "human_numeric_accuracy": "",
                "human_actionability": "",
                "human_causality_issue": "",
                "business_validation_passed": "" if business_validation_passed is None else business_validation_passed,
                "business_validation_details": business_validation_details or "",
                "weak_topics_covered": "" if weak_topics_covered is None else weak_topics_covered,
                "weak_topics_total": "" if weak_topics_total is None else weak_topics_total,
                "retrieved_source_ids": retrieved_source_ids or "",
                "cited_source_ids": cited_source_ids or "",
                "grounding_validation_passed": (
                    "" if grounding_validation_passed is None else grounding_validation_passed
                ),
                "grounding_validation_details": grounding_validation_details or "",
                "model_escalation_recommended": (
                    "" if model_escalation_recommended is None else model_escalation_recommended
                ),
                "final_needs_escalation": "" if final_needs_escalation is None else final_needs_escalation,
                "tour_module": tour_module or "",
                "tour_language": tour_language or "",
                "tour_step_index": "" if tour_step_index is None else tour_step_index,
                "tour_action": tour_action or "",
                "tour_decision_valid": "" if tour_decision_valid is None else tour_decision_valid,
                "tour_decision_error": tour_decision_error or "",
            }
        )

    return run_id


def save_human_evaluation(
    run_id: str,
    answer_key_correct: Optional[str] = None,
    groundedness: Optional[str] = None,
    language_quality=None,
    notes: Optional[str] = None,
    numeric_accuracy: Optional[str] = None,
    actionability=None,
    causality_issue: Optional[str] = None,
    csv_path: Path = CSV_PATH,
) -> bool:
    """run_id ile eşleşen satıra insan değerlendirmesi alanlarını yazar.

    Yalnızca None olmayan parametreler ilgili sütunu günceller; bu sayede B1
    (answer_key_correct/groundedness/language_quality/notes) ve B6
    (groundedness/numeric_accuracy/actionability/language_quality/
    causality_issue/notes) aynı fonksiyonu kendi alt kümeleriyle kullanabilir.

    Eşleşen bir satır bulunamazsa dosyayı değiştirmeden False döner.
    """
    _migrate_csv_if_needed(csv_path)
    if not csv_path.exists():
        return False

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    found = False
    for row in rows:
        if row.get("run_id") == run_id:
            if answer_key_correct is not None:
                row["human_answer_key_correct"] = answer_key_correct
            if groundedness is not None:
                row["human_groundedness"] = groundedness
            if language_quality is not None:
                row["human_language_quality"] = language_quality
            if notes is not None:
                row["human_notes"] = notes
            if numeric_accuracy is not None:
                row["human_numeric_accuracy"] = numeric_accuracy
            if actionability is not None:
                row["human_actionability"] = actionability
            if causality_issue is not None:
                row["human_causality_issue"] = causality_issue
            found = True

    if not found:
        return False

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})

    return True


def read_evaluations_csv(csv_path: Path = CSV_PATH) -> str:
    """CSV dosyasının ham içeriğini döndürür (indirme butonu için)."""
    _migrate_csv_if_needed(csv_path)
    if not csv_path.exists():
        return ",".join(FIELDNAMES) + "\n"
    with open(csv_path, "r", encoding="utf-8") as f:
        return f.read()
