"""B1'in seçici Gemma 4 göçü sonrası doğru model kimliklerini kullandığını
doğrular: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4 31B (yeni), Qwen3
32B yalnızca teknik yedek. Eski (Frankfurt'ta çalışmayan) DeepSeek V3.2 /
Qwen3 Next 80B A3B kimliklerinin B1 kaynağında bulunmadığını da doğrular.
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.model_registry import PLAN_A, PLAN_B

B1_PAGE_PATH = Path(__file__).resolve().parent.parent / "app_pages" / "b1_content_generation.py"

OLD_BROKEN_MODEL_IDS = ["qwen.qwen3-next-80b-a3b-instruct", "deepseek.v3.2"]
NEW_MIXED_MODEL_IDS = ["qwen.qwen3-235b-a22b-2507", "google.gemma-4-31b", "qwen.qwen3-32b"]


def test_b1_source_no_longer_falls_back_to_old_broken_models():
    source = B1_PAGE_PATH.read_text(encoding="utf-8")
    for old_id in OLD_BROKEN_MODEL_IDS:
        assert old_id not in source, f"Eski/bozuk model kimliği hâlâ B1 kaynağında bulunuyor: {old_id}"


def test_b1_source_uses_new_mixed_qwen_gemma_defaults():
    source = B1_PAGE_PATH.read_text(encoding="utf-8")
    for new_id in NEW_MIXED_MODEL_IDS:
        assert new_id in source, f"Beklenen model kimliği B1 kaynağında bulunamadı: {new_id}"


def test_plan_a_is_qwen_plan_b_is_gemma():
    assert PLAN_A.display_name == "Qwen3 235B A22B 2507"
    assert PLAN_A.slot_label == "Qwen Planı"
    assert PLAN_B.display_name == "Gemma 4 31B"
    assert PLAN_B.slot_label == "Gemma Planı"


def test_b1_sidebar_uses_mixed_defaults_when_env_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("B1_MODEL_A", raising=False)
    monkeypatch.delenv("B1_MODEL_B", raising=False)
    monkeypatch.delenv("B1_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("TEXT_MODEL_A", raising=False)
    monkeypatch.delenv("TEXT_MODEL_B", raising=False)
    # Gerçek .env dosyası bu değişkenleri zaten ayarlamış olabilir; bu testin
    # kodun kendi fallback varsayılanını (değil .env'i) doğruladığından emin
    # olmak için load_dotenv'i devre dışı bırakıyoruz.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/b1_content_generation.py")
    at.run(timeout=15)
    assert at.exception == []

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "qwen.qwen3-235b-a22b-2507" in technical_details_code
    assert "google.gemma-4-31b" in technical_details_code
    assert "qwen.qwen3-32b" in technical_details_code
    for old_id in OLD_BROKEN_MODEL_IDS:
        assert old_id not in technical_details_code


def test_b1_sidebar_backward_compatible_with_legacy_text_model_env(monkeypatch):
    """Yalnızca eski TEXT_MODEL_A/B ayarlanmış (yeni B1_MODEL_A/B ayarlanmamış)
    bir .env dosyası hâlâ çalışmalı (geriye dönük uyumluluk)."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("B1_MODEL_A", raising=False)
    monkeypatch.delenv("B1_MODEL_B", raising=False)
    monkeypatch.setenv("TEXT_MODEL_A", "qwen.qwen3-235b-a22b-2507")
    monkeypatch.setenv("TEXT_MODEL_B", "qwen.qwen3-32b")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/b1_content_generation.py")
    at.run(timeout=15)
    assert at.exception == []

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "qwen.qwen3-235b-a22b-2507" in technical_details_code
    assert "qwen.qwen3-32b" in technical_details_code
