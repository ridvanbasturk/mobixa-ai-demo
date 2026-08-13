"""C1'in seçici Gemma 4 göçü sonrası doğru model kimliklerini kullandığını
doğrular: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4 31B (yeni), Qwen3
32B yalnızca teknik yedek.
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.model_registry import PLAN_A, PLAN_B

C1_PAGE_PATH = Path(__file__).resolve().parent.parent / "app_pages" / "c1_learning_path.py"

OLD_BROKEN_MODEL_IDS = ["qwen.qwen3-next-80b-a3b-instruct", "deepseek.v3.2"]
NEW_MIXED_MODEL_IDS = ["qwen.qwen3-235b-a22b-2507", "google.gemma-4-31b", "qwen.qwen3-32b"]


def test_c1_source_no_longer_falls_back_to_old_broken_models():
    source = C1_PAGE_PATH.read_text(encoding="utf-8")
    for old_id in OLD_BROKEN_MODEL_IDS:
        assert old_id not in source, f"Eski/bozuk model kimliği hâlâ C1 kaynağında bulunuyor: {old_id}"


def test_c1_source_uses_new_mixed_qwen_gemma_defaults():
    source = C1_PAGE_PATH.read_text(encoding="utf-8")
    for new_id in NEW_MIXED_MODEL_IDS:
        assert new_id in source, f"Beklenen model kimliği C1 kaynağında bulunamadı: {new_id}"


def test_plan_a_is_qwen_plan_b_is_gemma():
    assert PLAN_A.display_name == "Qwen3 235B A22B 2507"
    assert PLAN_B.display_name == "Gemma 4 31B"


def test_c1_sidebar_uses_mixed_defaults_when_env_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("C1_MODEL_A", raising=False)
    monkeypatch.delenv("C1_MODEL_B", raising=False)
    monkeypatch.delenv("C1_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("TEXT_MODEL_A", raising=False)
    monkeypatch.delenv("TEXT_MODEL_B", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/c1_learning_path.py")
    at.run(timeout=15)
    assert at.exception == []

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "qwen.qwen3-235b-a22b-2507" in technical_details_code
    assert "google.gemma-4-31b" in technical_details_code
    assert "qwen.qwen3-32b" in technical_details_code
