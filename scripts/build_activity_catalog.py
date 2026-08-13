"""Gerçek aktivite JSON'larından (yönetici tarafından paylaşılan S3
export'ları) sample_data/activity_catalog.csv dosyasını türetir.

Kullanım:
    python scripts/build_activity_catalog.py
    python scripts/build_activity_catalog.py --input-dir docs/Journey_Json_ve_ssler

Her aktivite JSON'undan yalnızca üst seviye metadata okunur (activityId,
title, activityType, activitySubType, timeLimit, questionCount); soru
içerikleri (questions) kataloğa YAZILMAZ, yalnızca `topic` ve süre tahmini
türetmek için okunur. Hiçbir alan uydurulmaz — bir JSON'da beklenen alan
eksikse o dosya atlanır ve uyarı yazdırılır.

LEARN tipi aktiviteler bu script'in girdisinde hiç bulunmuyor (DB'den
geliyorlar, S3'te JSON'ları yok) — bu yüzden üretilen katalogda da yer
almazlar. Yönetici ileride LEARN JSON/DB şeması paylaşırsa bu script
genişletilmelidir.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "docs" / "Journey_Json_ve_ssler"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "sample_data" / "activity_catalog.csv"

CATALOG_COLUMNS = [
    "id",
    "title",
    "activity_type",
    "activity_sub_type",
    "topic",
    "duration_minutes",
    "question_count",
]

REQUIRED_TOP_LEVEL_FIELDS = ["activityId", "title", "activityType", "activitySubType"]


def _derive_topic(questions: Dict) -> str:
    """questions{categoryId: [soru...]} içindeki en sık geçen `category`
    string'ini döner. Hiç dolu category yoksa 'Genel' döner (uydurma bir
    konu adı değil, açık bir varsayılan)."""
    categories = Counter()
    for question_list in questions.values():
        if not isinstance(question_list, list):
            continue
        for question in question_list:
            category = question.get("category") if isinstance(question, dict) else None
            if category:
                categories[category] += 1
    if not categories:
        return "Genel"
    return categories.most_common(1)[0][0]


def _derive_duration_minutes(activity: Dict, questions: Dict) -> int:
    """timeLimit doluysa onu kullanır (TEST aktivitelerinde dakika olarak
    geliyor). Aksi halde tüm soruların `duration` (saniye) alanlarının
    toplamını 60'a bölüp yuvarlar (GAME aktivitelerinde timeLimit=0)."""
    time_limit = activity.get("timeLimit")
    if isinstance(time_limit, (int, float)) and time_limit > 0:
        return int(time_limit)

    total_seconds = 0
    for question_list in questions.values():
        if not isinstance(question_list, list):
            continue
        for question in question_list:
            duration = question.get("duration") if isinstance(question, dict) else None
            if isinstance(duration, (int, float)):
                total_seconds += duration

    if total_seconds <= 0:
        return 1
    return max(1, round(total_seconds / 60))


def _count_questions(questions: Dict) -> int:
    total = 0
    for question_list in questions.values():
        if isinstance(question_list, list):
            total += len(question_list)
    return total


def build_catalog_row(activity: Dict, source_file: str) -> Optional[Dict]:
    missing = [f for f in REQUIRED_TOP_LEVEL_FIELDS if not activity.get(f)]
    if missing:
        print(f"[atlandı] {source_file}: eksik alan(lar) {missing}")
        return None

    questions = activity.get("questions") or {}
    if not isinstance(questions, dict):
        questions = {}

    question_count = activity.get("questionCount")
    if not isinstance(question_count, (int, float)):
        question_count = _count_questions(questions)

    return {
        "id": str(activity["activityId"]),
        "title": activity["title"],
        "activity_type": activity["activityType"],
        "activity_sub_type": activity["activitySubType"],
        "topic": _derive_topic(questions),
        "duration_minutes": _derive_duration_minutes(activity, questions),
        "question_count": int(question_count),
    }


def build_catalog(input_dir: Path) -> List[Dict]:
    rows: List[Dict] = []
    seen_ids = set()
    for json_path in sorted(input_dir.glob("*.json")):
        try:
            activity = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[atlandı] {json_path.name}: okunamadı ({exc})")
            continue

        if not isinstance(activity, dict):
            print(f"[atlandı] {json_path.name}: beklenen JSON nesnesi değil")
            continue

        row = build_catalog_row(activity, json_path.name)
        if row is None:
            continue
        if row["id"] in seen_ids:
            print(f"[atlandı] {json_path.name}: activityId {row['id']} zaten katalogda")
            continue
        seen_ids.add(row["id"])
        rows.append(row)

    rows.sort(key=lambda r: r["id"])
    return rows


def write_catalog_csv(rows: List[Dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    if not args.input_dir.exists():
        raise SystemExit(f"Girdi dizini bulunamadı: {args.input_dir}")

    rows = build_catalog(args.input_dir)
    if not rows:
        raise SystemExit(f"{args.input_dir} içinde geçerli aktivite JSON'u bulunamadı.")

    write_catalog_csv(rows, args.output)
    print(f"{len(rows)} aktivite yazıldı -> {args.output}")


if __name__ == "__main__":
    main()
