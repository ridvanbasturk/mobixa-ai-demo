"""Tur ajanının kararlarının deterministik doğrulaması.

C1'in `validate_business_rules` deseniyle aynı felsefe: model çıktısı asla
gizlenmez, yalnızca bir doğrulama raporu üretilir. Fark şudur — burada
doğrulama BAŞARISIZ olursa adım ÇALIŞTIRILMAZ, çünkü var olmayan bir öğeye
tıklamak imlecin boşluğa gitmesine ve videonun bozulmasına yol açar.

Ajanın canlı sürülmesi bozulmaz: model yine her adımda o anki ekrana bakıp
kendi kararını verir; bu katman yalnızca kararın FİZİKSEL OLARAK MÜMKÜN
olduğunu garanti eder.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from schemas.tour_models import (
    ACTIONS_REQUIRING_ELEMENT,
    ACTION_TYPE,
    TourElement,
    TourStepDecision,
)

# Aynı (eylem, öğe) çiftinin arka arkaya kaç kez tekrarlanmasına izin verilir.
# Bu sınır aşılırsa ajan bir döngüye takılmıştır ve tur sonlandırılır.
MAX_CONSECUTIVE_REPEATS = 3


def decision_signature(decision: TourStepDecision, element: Optional[TourElement] = None) -> str:
    """Döngü tespiti için adım imzası.

    KRİTİK: imza `element_index` ÜZERİNDEN kurulamaz. İndeks konumsaldır —
    sayfada bir öğe belirip kaybolduğunda tüm numaralar kayar, dolayısıyla
    ajan aynı butona basmaya devam etse bile imza her seferinde değişir ve
    döngü fark edilmez (bu hata gerçek bir kayıtta ajanın aynı radyo butonuna
    8 kez basmasına yol açtı). Bu yüzden öğenin KALICI KİMLİĞİ kullanılır:
    Streamlit anahtarı varsa o, yoksa görünen adı.
    """
    if element is not None:
        identity = element.key or element.name or f"idx{element.index}"
    else:
        identity = "none"
    return f"{decision.action}:{identity}"


def validate_decision_against_inventory(
    decision: TourStepDecision,
    inventory: List[TourElement],
    recent_signatures: Optional[List[str]] = None,
) -> Dict:
    """Kararı canlı öğe envanterine göre denetler.

    Döner: {"valid": bool, "errors": [str], "element": TourElement|None,
            "signature": str}
    """
    errors: List[str] = []
    element: Optional[TourElement] = None

    by_index = {e.index: e for e in inventory}

    if decision.action in ACTIONS_REQUIRING_ELEMENT:
        if decision.element_index is None:
            errors.append(f"'{decision.action}' eylemi bir element_index gerektirir ama verilmedi.")
        elif decision.element_index not in by_index:
            errors.append(
                f"Ekranda böyle bir öğe yok: element_index={decision.element_index}. "
                f"Geçerli aralık: {min(by_index) if by_index else '-'}..{max(by_index) if by_index else '-'}"
            )
        else:
            element = by_index[decision.element_index]
            if not element.enabled:
                errors.append(f"Öğe devre dışı, etkileşim kurulamaz: [{element.index}] \"{element.name}\"")

    if decision.action == ACTION_TYPE and not (decision.text or "").strip():
        errors.append("'type' eylemi boş olmayan bir 'text' alanı gerektirir.")

    signature = decision_signature(decision, element)

    if recent_signatures:
        repeats = 0
        for previous in reversed(recent_signatures):
            if previous == signature:
                repeats += 1
            else:
                break
        if repeats >= MAX_CONSECUTIVE_REPEATS:
            target = f'"{element.name}"' if element else decision.action
            errors.append(
                f"Bu adımı zaten {repeats} kez arka arkaya yaptın ({target}) — ekran değişmiyor. "
                "Farklı bir öğe seç: sayfanın ASIL eylemini (üretim/gönderim butonu) çalıştır "
                "veya turu 'done' ile bitir."
            )

    return {"valid": not errors, "errors": errors, "element": element, "signature": signature}
