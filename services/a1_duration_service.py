"""A1 için deterministik sahne süresi tahmini (Faz 4C).

Model bir metin ÖNERİSİNDE bulunabilir; ancak nihai önerilen süre HER ZAMAN
Python tarafından, anlatım (narration) uzunluğu ve eylem türünden
deterministik olarak hesaplanır. Hiçbir LLM çağrısı yapmaz.
"""
from __future__ import annotations

MIN_SCENE_DURATION_SECONDS = 5.0
MAX_SCENE_DURATION_SECONDS = 14.0
DURATION_SOURCE = "deterministic_text_estimate"

WORDS_PER_SECOND = 2.3

# Eylem türüne göre yönelim/etkileşim payı (saniye): kullanıcının ekranı
# okuyup ilgili öğeyi bulması ve eylemi gerçekleştirmesi için gereken ek
# süre. "information"/"review" gibi yalnızca gözden geçirme gerektiren
# eylemler daha az, veri girişi gerektiren eylemler daha fazla pay alır.
ACTION_TYPE_ALLOWANCE_SECONDS = {
    "click": 2.0,
    "enter_text": 2.5,
    "select": 2.5,
    "review": 2.0,
    "information": 1.5,
}
DEFAULT_ACTION_ALLOWANCE_SECONDS = 2.0


def _word_count(text: str) -> int:
    return len((text or "").split())


def estimate_recommended_duration(narration: str, action_type: str) -> float:
    """Anlatım uzunluğu ve eylem türünden deterministik önerilen süreyi hesaplar.

    reading_seconds = kelime_sayısı / 2.3
    + eylem türüne göre yönelim/etkileşim payı
    ardından [5, 14] aralığına kırpılır ve en yakın 0.5 saniyeye yuvarlanır.
    """
    reading_seconds = _word_count(narration) / WORDS_PER_SECOND
    allowance = ACTION_TYPE_ALLOWANCE_SECONDS.get(action_type, DEFAULT_ACTION_ALLOWANCE_SECONDS)
    raw_duration = reading_seconds + allowance

    clamped = max(MIN_SCENE_DURATION_SECONDS, min(MAX_SCENE_DURATION_SECONDS, raw_duration))
    rounded = round(clamped * 2) / 2
    return rounded


def reading_seconds_for(narration: str) -> float:
    """Yalnızca okuma süresini (yönelim payı olmadan) döner; manuel süre
    uyarısı eşiği (`reading_seconds + 0.5`) hesaplamak için kullanılır."""
    return _word_count(narration) / WORDS_PER_SECOND


def manual_duration_warning(narration: str, manual_duration_seconds: float) -> str | None:
    """Kullanıcının elle seçtiği süre, anlatımın okunması için yeterli değilse
    bir Türkçe uyarı metni döner; yeterliyse None döner. Video üretimini
    ENGELLEMEZ — yalnızca bilgilendirme amaçlıdır."""
    minimum_acceptable = reading_seconds_for(narration) + 0.5
    if manual_duration_seconds < minimum_acceptable:
        return (
            f"Seçili süre ({manual_duration_seconds:.1f} sn), anlatımın okunması için "
            f"gereken tahmini süreden ({minimum_acceptable:.1f} sn) kısa. Video yine de "
            "oluşturulabilir, ancak altyazı ekranda kısa süre görünebilir."
        )
    return None
