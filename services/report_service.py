"""B6 için deterministik rapor metrikleri hesaplama ve rakamsal doğrulama.

Tüm sayısal hesaplamalar (ağırlıklı ortalamalar, risk kodları, en düşük/en
yüksek gruplar) burada Python/pandas ile yapılır. Modele yalnızca bu
fonksiyonların ürettiği metrik JSON'u gönderilir; model hiçbir yeni
aritmetik işlem yapmaz.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

REQUIRED_COLUMNS = [
    "user_group",
    "journey",
    "completion_rate",
    "quiz_score",
    "inactive_days",
    "active_users",
]

_NUMERIC_COLUMNS = ["completion_rate", "quiz_score", "inactive_days", "active_users"]

NUMERIC_TOLERANCE = 0.05


def load_and_validate_report(csv_source) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """CSV'yi okur, sütunları doğrular ve sayısal alanları güvenle dönüştürür.

    Başarısızlık durumunda (eksik sütun, geçersiz sayı, bozuk dosya) DataFrame
    yerine anlaşılır bir Türkçe hata mesajı döner; uygulama çökmez.
    """
    try:
        df = pd.read_csv(csv_source)
    except Exception as exc:  # noqa: BLE001 - herhangi bir okuma hatası kullanıcıya gösterilir
        return None, f"CSV dosyası okunamadı: {exc}"

    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return None, (
            f"Eksik sütun(lar): {', '.join(missing)}. "
            f"Gerekli sütunlar: {', '.join(REQUIRED_COLUMNS)}"
        )

    df = df.copy()
    for col in _NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    invalid_cols = [c for c in _NUMERIC_COLUMNS if df[c].isnull().any()]
    if invalid_cols:
        return None, (
            f"Sayısal sütunlarda geçersiz veri bulundu: {', '.join(invalid_cols)}. "
            "Lütfen bu sütunların yalnızca sayı içerdiğinden emin olun."
        )

    if df.empty:
        return None, "CSV dosyası boş; en az bir satır veri gerekli."

    df["user_group"] = df["user_group"].astype(str).str.strip()
    df["journey"] = df["journey"].astype(str).str.strip()

    return df, None


def _risk_codes_for_row(completion_rate: float, quiz_score: float, inactive_days: float) -> List[str]:
    codes: List[str] = []

    if completion_rate < 50:
        codes.append("completion_below_50")
    elif completion_rate < 70:
        codes.append("completion_below_70")

    if quiz_score < 60:
        codes.append("quiz_score_below_60")

    if inactive_days > 7:
        codes.append("inactive_days_above_7")
    elif inactive_days > 4:
        codes.append("inactive_days_above_4")

    return codes


def compute_report_metrics(df: pd.DataFrame, report_period: str) -> Dict:
    """Deterministik rapor metriklerini hesaplar.

    Toplam aktif kullanıcı sayısı sıfırsa ValueError fırlatır (rapor
    oluşturulamaz, modele hiçbir çağrı yapılmaz).
    """
    total_active_users = int(df["active_users"].sum())
    if total_active_users <= 0:
        raise ValueError("Toplam aktif kullanıcı sayısı sıfır; rapor metrikleri hesaplanamıyor.")

    weighted_completion = (df["completion_rate"] * df["active_users"]).sum() / total_active_users
    weighted_quiz = (df["quiz_score"] * df["active_users"]).sum() / total_active_users

    group_metrics = []
    for _, row in df.iterrows():
        group_label = f"{row['user_group']} — {row['journey']}"
        risk_codes = _risk_codes_for_row(
            float(row["completion_rate"]), float(row["quiz_score"]), float(row["inactive_days"])
        )
        group_metrics.append(
            {
                "group": group_label,
                "user_group": row["user_group"],
                "journey": row["journey"],
                "completion_rate": round(float(row["completion_rate"]), 1),
                "quiz_score": round(float(row["quiz_score"]), 1),
                "inactive_days": int(row["inactive_days"]),
                "active_users": int(row["active_users"]),
                "risk_codes": risk_codes,
            }
        )

    lowest_completion = min(group_metrics, key=lambda g: g["completion_rate"])
    highest_completion = max(group_metrics, key=lambda g: g["completion_rate"])
    lowest_quiz = min(group_metrics, key=lambda g: g["quiz_score"])
    highest_quiz = max(group_metrics, key=lambda g: g["quiz_score"])

    risk_groups = [
        {"group": g["group"], "risk_codes": g["risk_codes"]} for g in group_metrics if g["risk_codes"]
    ]

    return {
        "report_period": report_period,
        "total_active_users": total_active_users,
        "overall_completion_rate": round(weighted_completion, 1),
        "overall_average_quiz_score": round(weighted_quiz, 1),
        "lowest_completion_group": lowest_completion["group"],
        "highest_completion_group": highest_completion["group"],
        "lowest_quiz_group": lowest_quiz["group"],
        "highest_quiz_group": highest_quiz["group"],
        "group_metrics": group_metrics,
        "risk_groups": risk_groups,
    }


_NUMBER_PATTERN = re.compile(r"-?\d+(?:[.,]\d+)?")


def _extract_numbers(text: str) -> List[float]:
    numbers = []
    for match in _NUMBER_PATTERN.finditer(text or ""):
        raw = match.group().replace(",", ".")
        try:
            numbers.append(float(raw))
        except ValueError:
            continue
    return numbers


def _collect_metric_numbers(metrics: Dict) -> List[float]:
    numbers: List[float] = []

    def _walk(value):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            numbers.append(float(value))
        elif isinstance(value, dict):
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for v in value:
                _walk(v)

    _walk(metrics)
    return numbers


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def validate_numeric_grounding(insights: List[Dict], metrics: Dict) -> Tuple[bool, List[str]]:
    """finding/evidence metinlerindeki sayıları metrik JSON'undaki sayılarla karşılaştırır.

    Başlıklardaki (title) sayılar yok sayılır. Ondalık nokta ve Türkçe ondalık
    virgülü desteklenir. 42 ve 42.0 eşit kabul edilir (küçük bir tolerans ile).
    Metriklerde bulunmayan sayılar için uyarı metinleri döner; model çıktısı
    doğrulama başarısız olsa bile gizlenmez.
    """
    metric_numbers = _collect_metric_numbers(metrics)
    warnings: List[str] = []

    for insight in insights:
        finding = insight.get("finding", "") if isinstance(insight, dict) else getattr(insight, "finding", "")
        evidence = insight.get("evidence", "") if isinstance(insight, dict) else getattr(insight, "evidence", "")
        combined_text = f"{finding} {evidence}"

        for number in _extract_numbers(combined_text):
            if not any(abs(number - m) <= NUMERIC_TOLERANCE for m in metric_numbers):
                warnings.append(_format_number(number))

    # Sırayı koruyarak tekrarları temizle
    warnings = list(dict.fromkeys(warnings))
    passed = len(warnings) == 0
    return passed, warnings
