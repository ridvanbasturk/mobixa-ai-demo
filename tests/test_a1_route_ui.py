"""A1 sidebar'ında model-bilinçli Mantle rota metadatasının gösterildiğini
doğrulayan Streamlit AppTest testi. Hiçbir gerçek Bedrock çağrısı yapmaz.
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_gemma_route_metadata_shown_in_sidebar(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.setenv("A1_VISION_MODEL_A", "qwen.qwen3-vl-235b-a22b-instruct")
    monkeypatch.setenv("A1_VISION_MODEL_B", "google.gemma-4-31b")

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    assert at.exception == []

    code_blocks = [c.value for c in at.sidebar.get("code")]
    combined = "\n".join(code_blocks)
    assert "Standart /v1" in combined
    assert "OpenAI uyumlu /openai/v1" in combined

    captions = [c.value for c in at.sidebar.get("caption")]
    assert any("OpenAI uyumlu rotasını kullanır" in c for c in captions)


def test_qwen_only_route_metadata_shown_when_no_gemma(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.setenv("A1_VISION_MODEL_A", "qwen.qwen3-vl-235b-a22b-instruct")
    monkeypatch.setenv("A1_VISION_MODEL_B", "qwen.qwen3-vl-235b-a22b-instruct")
    # Bu test yalnızca Qwen senaryosunu doğrular; gerçek .env'in
    # A1_STORYBOARD_MODEL_B'yi Gemma'ya ayarlamış olabileceği ihtimaline karşı
    # storyboard modellerini de açıkça Qwen'e sabitliyoruz.
    monkeypatch.setenv("A1_STORYBOARD_MODEL_A", "qwen.qwen3-235b-a22b-2507")
    monkeypatch.setenv("A1_STORYBOARD_MODEL_B", "qwen.qwen3-32b")

    at = AppTest.from_file("app_pages/a1_tutorial_video.py")
    at.run(timeout=15)
    assert at.exception == []

    code_blocks = [c.value for c in at.sidebar.get("code")]
    combined = "\n".join(code_blocks)
    assert "OpenAI uyumlu /openai/v1" not in combined

    captions = [c.value for c in at.sidebar.get("caption")]
    assert not any("OpenAI uyumlu rotasını kullanır" in c for c in captions)
