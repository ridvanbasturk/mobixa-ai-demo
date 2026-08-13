"""C1 (Journey Oluşturma) için Journey talebi (brief) / aktivite kataloğu
doğrulama ve deterministik iş kuralı doğrulaması.

Model yalnızca katalogdaki mevcut aktiviteleri seçip sıralayabilir; hangi
aktivitenin geçerli olduğu, süre toplamının doğru olup olmadığı, zorunlu
konuların kapsanıp kapsanmadığı ve (isteniyorsa) Journey'nin bir sınavla
bitip bitmediği burada Python ile deterministik olarak kontrol edilir.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

REQUIRED_BRIEF_FIELDS = [
    "journey_name",
    "journey_type",
    "audience_description",
    "goal_description",
    "required_topics",
    "excluded_activity_ids",
    "min_activities",
    "max_activities",
    "must_end_with_test",
]

REQUIRED_CATALOG_COLUMNS = [
    "id",
    "title",
    "activity_type",
    "activity_sub_type",
    "topic",
    "duration_minutes",
    "question_count",
]

ALLOWED_JOURNEY_TYPES = {"Private", "Public"}
ALLOWED_ACTIVITY_TYPES = {"GAME", "TEST", "LEARN"}


def _load_json_source(json_source) -> Tuple[Optional[dict], Optional[str]]:
    try:
        if isinstance(json_source, dict):
            return json_source, None
        if isinstance(json_source, (str, Path)):
            with open(json_source, "r", encoding="utf-8") as f:
                return json.load(f), None
        if hasattr(json_source, "read"):
            raw = json_source.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw), None
        return None, "Desteklenmeyen brief veri türü."
    except Exception as exc:  # noqa: BLE001 - herhangi bir okuma/ayrıştırma hatası kullanıcıya gösterilir
        return None, f"Journey talebi JSON dosyası okunamadı: {exc}"


def load_and_validate_journey_brief(json_source) -> Tuple[Optional[Dict], Optional[str]]:
    """Journey talebi (brief) JSON'unu okur ve iş kurallarına göre doğrular."""
    data, error = _load_json_source(json_source)
    if error:
        return None, error

    if not isinstance(data, dict):
        return None, "Journey talebi JSON'u bir nesne (obje) olmalı."

    missing = [f for f in REQUIRED_BRIEF_FIELDS if f not in data]
    if missing:
        return None, f"Eksik brief alan(lar)ı: {', '.join(missing)}"

    for field in ("journey_name", "audience_description", "goal_description"):
        if not isinstance(data[field], str) or not data[field].strip():
            return None, f"'{field}' boş olamaz."

    if data["journey_type"] not in ALLOWED_JOURNEY_TYPES:
        return None, f"journey_type yalnızca {sorted(ALLOWED_JOURNEY_TYPES)} olabilir."

    for field in ("required_topics", "excluded_activity_ids"):
        if not isinstance(data[field], list):
            return None, f"'{field}' bir liste (array) olmalı."

    min_activities = data["min_activities"]
    max_activities = data["max_activities"]
    for field, value in (("min_activities", min_activities), ("max_activities", max_activities)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None, f"'{field}' pozitif bir tam sayı olmalı."
    if min_activities > max_activities:
        return None, "min_activities, max_activities değerinden büyük olamaz."

    if not isinstance(data["must_end_with_test"], bool):
        return None, "must_end_with_test true/false olmalı."

    return data, None


def load_and_validate_catalog(csv_source) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Aktivite kataloğu CSV'sini okur, sütunları ve değerleri doğrular."""
    try:
        df = pd.read_csv(csv_source)
    except Exception as exc:  # noqa: BLE001
        return None, f"CSV dosyası okunamadı: {exc}"

    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_CATALOG_COLUMNS if c not in df.columns]
    if missing:
        return None, (
            f"Eksik sütun(lar): {', '.join(missing)}. "
            f"Gerekli sütunlar: {', '.join(REQUIRED_CATALOG_COLUMNS)}"
        )

    df = df.copy()
    for col in ["id", "title", "activity_type", "activity_sub_type", "topic"]:
        df[col] = df[col].astype(str).str.strip()

    if (df["id"] == "").any() or (df["id"].str.lower() == "nan").any():
        return None, "Aktivite kimlikleri (id) boş olamaz."

    if df["id"].duplicated().any():
        dupes = sorted(df.loc[df["id"].duplicated(), "id"].unique().tolist())
        return None, f"Tekrarlanan aktivite kimlikleri bulundu: {', '.join(dupes)}"

    for col in ["title", "activity_type", "topic"]:
        if (df[col] == "").any() or (df[col].str.lower() == "nan").any():
            return None, f"'{col}' sütunu boş olamaz."

    invalid_type = ~df["activity_type"].isin(ALLOWED_ACTIVITY_TYPES)
    if invalid_type.any():
        bad_values = sorted(df.loc[invalid_type, "activity_type"].unique().tolist())
        return None, (
            f"Geçersiz activity_type değeri (yalnızca {sorted(ALLOWED_ACTIVITY_TYPES)} olabilir): "
            f"{', '.join(bad_values)}"
        )

    for col in ["duration_minutes", "question_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isnull().any():
            return None, f"'{col}' sütunu geçerli bir sayı içermeli."
        if (df[col] < 0).any():
            return None, f"'{col}' sütunu negatif olamaz."
        if not (df[col] % 1 == 0).all():
            return None, f"'{col}' tam sayı olmalı (ondalık olamaz)."
        df[col] = df[col].astype(int)

    if (df["duration_minutes"] <= 0).any():
        return None, "duration_minutes pozitif bir tam sayı olmalı."

    return df, None


def find_unknown_excluded_ids(brief: Dict, catalog_df: pd.DataFrame) -> List[str]:
    """Brief'teki hariç tutulacak aktivite kimliklerinden katalogda bulunmayanları döner.

    Bu bir uyarıdır, hata değildir; uygulama çökmez.
    """
    catalog_ids = set(catalog_df["id"])
    return [aid for aid in brief.get("excluded_activity_ids", []) if aid not in catalog_ids]


def validate_business_rules(
    recommended_activities: List[Dict],
    total_minutes_declared: int,
    brief: Dict,
    catalog_df: pd.DataFrame,
) -> Dict:
    """Model tarafından üretilen Journey'i deterministik iş kurallarına göre doğrular.

    Model çıktısı bir hata durumunda bile gizlenmez; bu fonksiyon yalnızca
    bir doğrulama raporu (errors/warnings) üretir.
    """
    errors: List[str] = []
    warnings: List[str] = []

    catalog_by_id = {row["id"]: row for _, row in catalog_df.iterrows()}
    excluded_ids = set(brief.get("excluded_activity_ids", []))
    required_topics = set(brief.get("required_topics", []))
    min_activities = brief.get("min_activities")
    max_activities = brief.get("max_activities")
    must_end_with_test = brief.get("must_end_with_test", False)

    orders = [item["order"] for item in recommended_activities]
    expected_orders = list(range(1, len(recommended_activities) + 1))
    if sorted(orders) != expected_orders:
        errors.append("Sıra numaraları (order) 1'den başlayarak ardışık olmalı.")

    seen_ids: set = set()
    covered_required_topics: set = set()
    duration_sum = 0
    enriched_activities: List[Dict] = []

    for item in recommended_activities:
        activity_id = item["activity_id"]

        if activity_id in seen_ids:
            errors.append(f"Aktivite birden fazla kez seçilmiş: {activity_id}")
        seen_ids.add(activity_id)

        if activity_id in excluded_ids:
            errors.append(f"Hariç tutulması gereken bir aktivite seçilmiş: {activity_id}")

        catalog_row = catalog_by_id.get(activity_id)
        if catalog_row is None:
            errors.append(f"Katalogda bulunmayan aktivite kimliği: {activity_id}")
            enriched_activities.append(
                {
                    **item,
                    "title": None,
                    "activity_type": None,
                    "activity_sub_type": None,
                    "topic": None,
                    "duration_minutes": None,
                }
            )
            continue

        catalog_duration = int(catalog_row["duration_minutes"])
        if item["estimated_minutes"] != catalog_duration:
            errors.append(
                f"{activity_id} için tahmini süre katalogla uyuşmuyor: "
                f"model {item['estimated_minutes']} dk, katalog {catalog_duration} dk"
            )

        duration_sum += catalog_duration
        if catalog_row["topic"] in required_topics:
            covered_required_topics.add(catalog_row["topic"])

        enriched_activities.append(
            {
                **item,
                "title": catalog_row["title"],
                "activity_type": catalog_row["activity_type"],
                "activity_sub_type": catalog_row["activity_sub_type"],
                "topic": catalog_row["topic"],
                "duration_minutes": catalog_duration,
            }
        )

    if total_minutes_declared != duration_sum:
        errors.append(
            f"Toplam süre tutarsız: model {total_minutes_declared} dk bildirdi, "
            f"katalogdan hesaplanan toplam {duration_sum} dk"
        )

    activity_count = len(recommended_activities)
    if min_activities is not None and activity_count < min_activities:
        errors.append(f"Aktivite sayısı minimum sınırın altında: {activity_count} < {min_activities}")
    if max_activities is not None and activity_count > max_activities:
        errors.append(f"Aktivite sayısı maksimum sınırı aşıyor: {activity_count} > {max_activities}")

    if must_end_with_test and enriched_activities:
        last_activity = max(enriched_activities, key=lambda a: a["order"])
        if last_activity.get("activity_type") != "TEST":
            errors.append(
                "must_end_with_test aktif ama Journey bir TEST tipi aktiviteyle bitmiyor "
                f"(son aktivite: {last_activity.get('activity_type') or 'bilinmiyor'})."
            )

    required_topics_total = len(required_topics)
    required_topics_covered = len(covered_required_topics)
    if required_topics_total > 0 and required_topics_covered < required_topics_total:
        uncovered = sorted(required_topics - covered_required_topics)
        errors.append("Şu zorunlu konu(lar) hiçbir aktivite ile kapsanmıyor: " + ", ".join(uncovered))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "required_topics_covered": required_topics_covered,
        "required_topics_total": required_topics_total,
        "enriched_path": enriched_activities,
        "total_minutes_calculated": duration_sum,
    }
