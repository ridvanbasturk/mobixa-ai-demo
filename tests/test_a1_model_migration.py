"""A1'in seçici Gemma 4 göçü sonrası doğru model yapılandırmasını
kullandığını doğrular:
  - Storyboard: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4 31B (yeni),
    Qwen3 32B yalnızca teknik yedek (A1_STORYBOARD_FALLBACK).
  - Vision: Qwen3 VL 235B (korunur, Plan A) + Gemma 4 31B (gerçek görsel
    girişle doğrulanmış, Plan B).
  - Sahne genişletme: varsayılan TEK aktif model Gemma 4 31B (maliyet için);
    Qwen3 235B seçilebilir bir alternatiftir.
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.model_registry import A1_PLAN_A, A1_PLAN_B, A1_VISION_PLAN_A, A1_VISION_PLAN_B

A1_PAGE_PATH = Path(__file__).resolve().parent.parent / "app_pages" / "a1_tutorial_video.py"


def test_a1_plan_labels_are_qwen_and_gemma():
    assert A1_PLAN_A.slot_label == "Qwen Planı"
    assert A1_PLAN_A.display_name == "Qwen3 235B A22B 2507"
    assert A1_PLAN_B.slot_label == "Gemma Planı"
    assert A1_PLAN_B.display_name == "Gemma 4 31B"


def test_a1_vision_plan_labels_are_qwen_vl_and_gemma():
    assert A1_VISION_PLAN_A.display_name == "Qwen3 VL 235B A22B"
    assert A1_VISION_PLAN_B.display_name == "Gemma 4 31B"


def test_a1_source_contains_storyboard_and_expansion_defaults():
    source = A1_PAGE_PATH.read_text(encoding="utf-8")
    assert "A1_STORYBOARD_MODEL_A" in source
    assert "A1_STORYBOARD_MODEL_B" in source
    assert "A1_STORYBOARD_FALLBACK" in source
    assert "A1_EXPANSION_MODEL" in source
    assert "A1_EXPANSION_ALT_MODEL" in source
    assert "google.gemma-4-31b" in source
    assert "qwen.qwen3-235b-a22b-2507" in source
    assert "qwen.qwen3-32b" in source


def test_a1_sidebar_storyboard_mixed_defaults_when_env_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    for key in [
        "A1_STORYBOARD_MODEL_A",
        "A1_STORYBOARD_MODEL_B",
        "A1_STORYBOARD_FALLBACK",
        "A1_MODEL_A",
        "A1_MODEL_B",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("A1_VISION_MODEL_A", "qwen.qwen3-vl-235b-a22b-instruct")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    assert at.exception == []

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "qwen.qwen3-235b-a22b-2507" in technical_details_code
    assert "google.gemma-4-31b" in technical_details_code
    assert "qwen.qwen3-32b" in technical_details_code


def test_a1_expansion_model_defaults_to_gemma(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("A1_EXPANSION_MODEL", raising=False)
    monkeypatch.delenv("A1_EXPANSION_ALT_MODEL", raising=False)
    monkeypatch.setenv("A1_VISION_MODEL_A", "qwen.qwen3-vl-235b-a22b-instruct")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    assert at.exception == []

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "Sahne genişletme modeli (varsayılan): google.gemma-4-31b" in technical_details_code
    assert "Sahne genişletme alternatifi: qwen.qwen3-235b-a22b-2507" in technical_details_code
