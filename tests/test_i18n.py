from services.i18n import LANG_EN, LANG_TR, LANGUAGE_STATE_KEY, TRANSLATIONS, t
from services.i18n import _LANGUAGE_WIDGET_KEY


def test_tr_and_en_have_identical_key_sets():
    tr_keys = set(TRANSLATIONS[LANG_TR].keys())
    en_keys = set(TRANSLATIONS[LANG_EN].keys())
    missing_in_en = tr_keys - en_keys
    missing_in_tr = en_keys - tr_keys
    assert not missing_in_en, f"EN'de eksik anahtarlar: {sorted(missing_in_en)}"
    assert not missing_in_tr, f"TR'de eksik anahtarlar: {sorted(missing_in_tr)}"


def test_no_blank_translation_values():
    for lang, entries in TRANSLATIONS.items():
        for key, value in entries.items():
            assert isinstance(value, str) and value.strip(), f"{lang}/{key} boş veya string değil"


def test_t_falls_back_to_tr_for_unknown_key_in_en(monkeypatch):
    import streamlit as st

    st.session_state["app_language"] = LANG_EN
    assert t("app.title") == "Mobixa AI Demo"


def test_t_returns_key_itself_when_missing_everywhere():
    import streamlit as st

    st.session_state["app_language"] = LANG_TR
    assert t("does.not.exist.anywhere") == "does.not.exist.anywhere"


def test_language_widget_key_is_decoupled_from_state_key():
    # Regresyon koruması: dil seçici widget'ının `key`'i, kalıcı
    # LANGUAGE_STATE_KEY ile AYNI olmamalı. Aynı olursa, Streamlit
    # st.navigation ile sayfa değiştirildiğinde önceki sayfanın widget'ına
    # bağlı session_state anahtarı temizlenir ve dil sessizce varsayılana
    # (TR) döner — bu proje daha önce tam olarak bu hatayı yaşadı.
    assert _LANGUAGE_WIDGET_KEY != LANGUAGE_STATE_KEY
