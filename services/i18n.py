"""Uygulama genelinde TR/EN dil desteği için çekirdek modül.

Dil seçimi `st.session_state["app_language"]` üzerinden tutulur; bu key
tüm Streamlit sayfaları arasında (aynı oturumda) paylaşılır, böylece bir
sayfada seçilen dil diğer sayfalara geçince de korunur.

Kapsam: yalnızca UI metinleri, sistem promptu seçimi ve modele gönderilen
beklenen çıktı dilini kapsar. Pydantic/iş kuralı ham hata mesajları
(schemas/*.py, validate_business_rules vb.) bilinçli olarak bu kapsamın
DIŞINDA tutulur — hem şemaların Streamlit'ten bağımsız kalması gereken
saf-Python doğası bozulmasın hem de bu mesajların tam Türkçe metnini
`assert` eden çok sayıda mevcut test kırılmasın diye.
"""
from __future__ import annotations

import streamlit as st

from services.i18n_strings.a1 import EN as _A1_EN, TR as _A1_TR  # A1 Tur Stüdyosu
from services.i18n_strings.a2 import EN as _A2_EN, TR as _A2_TR
from services.i18n_strings.b1 import EN as _B1_EN, TR as _B1_TR
from services.i18n_strings.b6 import EN as _B6_EN, TR as _B6_TR
from services.i18n_strings.c1 import EN as _C1_EN, TR as _C1_TR
from services.i18n_strings.common import EN as _COMMON_EN, TR as _COMMON_TR

LANG_TR = "tr"
LANG_EN = "en"
SUPPORTED_LANGUAGES = (LANG_TR, LANG_EN)
DEFAULT_LANGUAGE = LANG_TR
LANGUAGE_STATE_KEY = "app_language"

TRANSLATIONS = {
    LANG_TR: {**_COMMON_TR, **_B1_TR, **_B6_TR, **_C1_TR, **_A2_TR, **_A1_TR},
    LANG_EN: {**_COMMON_EN, **_B1_EN, **_B6_EN, **_C1_EN, **_A2_EN, **_A1_EN},
}

_LANGUAGE_LABELS = {LANG_TR: "TR", LANG_EN: "EN"}


def get_language() -> str:
    return st.session_state.get(LANGUAGE_STATE_KEY, DEFAULT_LANGUAGE)


def t(key: str) -> str:
    """Anahtarı geçerli dile çevirir.

    Anahtar geçerli dilde yoksa TR'ye düşer; TR'de de yoksa anahtarın
    kendisini döner (eksik çeviriyi sessizce yutmak yerine görünür kılar).
    """
    lang = get_language()
    value = TRANSLATIONS.get(lang, {}).get(key)
    if value is not None:
        return value
    return TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)


_LANGUAGE_WIDGET_KEY = "app_language_widget"


def render_language_switcher() -> None:
    """Ana içerik alanının sağ üstünde bir TR/EN segmented control render eder.

    ÖNEMLİ: widget'ın `key`'i (`_LANGUAGE_WIDGET_KEY`), gerçek kaynağın
    tutulduğu `LANGUAGE_STATE_KEY`'den BİLİNÇLİ olarak farklıdır. Streamlit
    (`st.navigation`/`st.Page` ile) sayfa değiştirildiğinde, bir önceki
    sayfada render edilmiş widget'lara bağlı `session_state` anahtarlarını
    "kullanılmayan widget" olarak temizleyebiliyor — bu, `key=` doğrudan
    `LANGUAGE_STATE_KEY` olsaydı her sayfa geçişinde dilin sessizce TR'ye
    dönmesine yol açıyordu (gözlemlenen hata). `LANGUAGE_STATE_KEY` hiçbir
    widget'a `key=` olarak verilmediği için bu temizlikten etkilenmez ve
    tüm sayfalar arasında güvenilir biçimde kalıcı olur; widget yalnızca
    ondan okuyup yazan ince bir katmandır.
    """
    if LANGUAGE_STATE_KEY not in st.session_state:
        st.session_state[LANGUAGE_STATE_KEY] = DEFAULT_LANGUAGE

    current = st.session_state[LANGUAGE_STATE_KEY]

    _spacer, control = st.columns([6, 1])
    with control:
        choice = st.segmented_control(
            "Dil / Language",
            options=list(SUPPORTED_LANGUAGES),
            format_func=lambda lang: _LANGUAGE_LABELS[lang],
            default=current,
            key=_LANGUAGE_WIDGET_KEY,
            label_visibility="collapsed",
        )

    if choice is not None and choice != current:
        st.session_state[LANGUAGE_STATE_KEY] = choice
        st.rerun()
