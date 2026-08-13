"""A1 Tur Stüdyosu sayfasının render testleri (tarayıcı/AWS gerekmez).

Sayfa yalnızca arayüzdür; "Turu Çek" butonuna BASILMAZ, bu yüzden gerçek bir
kayıt başlamaz.
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.tour_pipeline import TOUR_MODULES, compute_source_fingerprint, module_title

PAGE = "app_pages/a1_tour_studio.py"


def _run(language: str = "tr") -> AppTest:
    at = AppTest.from_file(PAGE)
    if language != "tr":
        at.session_state["app_language"] = language
    at.run(timeout=60)
    return at


def test_page_renders_without_exception_in_turkish():
    at = _run("tr")
    assert at.exception == []


def test_page_renders_without_exception_in_english():
    at = _run("en")
    assert at.exception == []


def test_page_title_switches_with_language():
    tr_subheaders = " ".join(s.value for s in _run("tr").subheader)
    en_subheaders = " ".join(s.value for s in _run("en").subheader)
    assert "Ürün Turu Stüdyosu" in tr_subheaders
    assert "Product Tour Studio" in en_subheaders


def test_module_selector_lists_every_tourable_module():
    # AppTest, seçenekleri format_func'tan geçmiş HÂLİYLE döndürür; bu yüzden
    # ham anahtarlarla değil, gösterilen başlıklarla karşılaştırılır.
    at = _run("tr")
    selectbox = next(s for s in at.selectbox if s.key == "a1_module")
    expected = {module_title(key, "tr") for key in TOUR_MODULES}
    assert set(selectbox.options) == expected


def test_cost_warning_is_always_shown():
    # Kayıt gerçek model çağrıları tetiklediği için maliyet uyarısı gizlenemez.
    at = _run("tr")
    info_text = " ".join(i.value for i in at.info)
    assert "Maliyet uyarısı" in info_text


def test_record_button_exists_but_is_not_pressed():
    at = _run("tr")
    assert any(b.key == "a1_record" for b in at.button)


def test_result_section_reports_nothing_recorded_yet():
    at = _run("tr")
    info_text = " ".join(i.value for i in at.info)
    assert "Henüz bir tur çekilmedi" in info_text


def test_voice_status_is_always_reported(monkeypatch):
    # Polly yoksa sayfa bunu SESSİZCE geçmemeli.
    at = _run("tr")
    reported = " ".join(w.value for w in at.warning) + " ".join(s.value for s in at.success)
    assert "eslendirme" in reported  # "Seslendirme" / "seslendirme"


def test_module_title_is_language_aware():
    assert "Journey" in module_title("c1", "tr")
    assert module_title("c1", "en") != module_title("c1", "tr")


def test_fingerprint_is_stable_and_changes_with_source(tmp_path, monkeypatch):
    first = compute_source_fingerprint("c1")
    assert first == compute_source_fingerprint("c1")  # kararlı
    assert len(first) == 16
    # Farklı modül farklı parmak izi üretir.
    assert compute_source_fingerprint("a2") != first


def test_every_tour_module_declares_existing_source_files():
    repo_root = Path(__file__).resolve().parent.parent
    for module, config in TOUR_MODULES.items():
        for relative in config["sources"]:
            assert (repo_root / relative).exists(), f"{module}: {relative} yok"
