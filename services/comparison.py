"""Ölçülebilir teknik verilere dayalı model karşılaştırma özeti.

Yalnızca ölçülen sayısal verilere (maliyet, gecikme, token) ve JSON/şema
doğrulama sonuçlarına dayanır. Anlamsal ("en doğru", "en kaliteli")
iddialarda bulunmaz — bunlar insan değerlendirmesi gerektirir.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from services.i18n_strings.common import EN as _COMMON_EN, TR as _COMMON_TR

_STRINGS = {"tr": _COMMON_TR, "en": _COMMON_EN}


@dataclass
class ModelMetrics:
    label: str
    cost: Optional[float]
    latency_ms: Optional[float]
    total_tokens: Optional[int]
    json_valid: bool
    schema_valid: bool
    # Yalnızca deterministik doğrulama (iş kuralı / dayanak vb.) yapan
    # özellikler (ör. C1, A2) tarafından doldurulur. None bırakılırsa
    # (B1/B6) karşılaştırma özetinde bu satır hiç üretilmez; mevcut
    # davranış değişmez.
    business_valid: Optional[bool] = None


def pick_lowest(entries: List[tuple]) -> Optional[List[str]]:
    """(label, value) çiftlerinden en düşük değere sahip olan(lar)ı döndürür.

    Değeri None olan girdiler yok sayılır. Hiçbir girdi ölçülmemişse None
    döner. Eşitlik durumunda birden fazla etiket döner.
    """
    measured = [(label, value) for label, value in entries if value is not None]
    if not measured:
        return None
    lowest_value = min(value for _, value in measured)
    return [label for label, value in measured if value == lowest_value]


def _format_winners(winners: List[str], prefix_single: str, prefix_tie: str, and_join: str) -> str:
    if len(winners) == 1:
        return f"{prefix_single}{winners[0]}"
    return f"{prefix_tie}{and_join.join(winners)}"


def build_comparison_summary(models: List[ModelMetrics], lang: str = "tr") -> List[str]:
    """Verilen model metriklerinden karşılaştırma mesajları üretir.

    `lang` varsayılan olarak "tr"dir (mevcut çağrılar/testler değişmeden
    çalışır); "en" geçilirse aynı mantık İngilizce metinlerle üretir.
    """
    s = _STRINGS.get(lang, _COMMON_TR)
    lines: List[str] = []

    cost_entries = [(m.label, m.cost) for m in models]
    cost_winners = pick_lowest(cost_entries)
    lines.append(
        s["common.comparison.cost_none"]
        if cost_winners is None
        else _format_winners(
            cost_winners,
            s["common.comparison.cost_winner_prefix"],
            s["common.comparison.cost_tie_prefix"],
            s["common.comparison.and_join"],
        )
    )

    latency_entries = [(m.label, m.latency_ms) for m in models]
    latency_winners = pick_lowest(latency_entries)
    lines.append(
        s["common.comparison.latency_none"]
        if latency_winners is None
        else _format_winners(
            latency_winners,
            s["common.comparison.latency_winner_prefix"],
            s["common.comparison.latency_tie_prefix"],
            s["common.comparison.and_join"],
        )
    )

    token_entries = [(m.label, m.total_tokens) for m in models]
    token_winners = pick_lowest(token_entries)
    lines.append(
        s["common.comparison.tokens_none"]
        if token_winners is None
        else _format_winners(
            token_winners,
            s["common.comparison.tokens_winner_prefix"],
            s["common.comparison.tokens_tie_prefix"],
            s["common.comparison.and_join"],
        )
    )

    if all(m.json_valid for m in models) and all(m.schema_valid for m in models):
        lines.append(s["common.comparison.both_json_schema_passed"])
    else:
        for m in models:
            json_status = s["common.comparison.status_passed"] if m.json_valid else s["common.comparison.status_failed"]
            schema_status = (
                s["common.comparison.status_passed"] if m.schema_valid else s["common.comparison.status_failed"]
            )
            lines.append(
                s["common.comparison.json_schema_line"].format(
                    label=m.label, json_status=json_status, schema_status=schema_status
                )
            )

    if all(m.business_valid is not None for m in models):
        if all(m.business_valid for m in models):
            lines.append(s["common.comparison.both_business_passed"])
        else:
            for m in models:
                status = s["common.comparison.status_passed"] if m.business_valid else s["common.comparison.status_failed"]
                lines.append(s["common.comparison.business_line"].format(label=m.label, status=status))

    return lines
