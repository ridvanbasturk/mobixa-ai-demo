"""A2'nin seçici Gemma 4 göçü sonrası TEK istisna olduğunu doğrular: aktif
yanıt üretim modelleri YALNIZCA Gemma'dır. Kimi K2.5 / DeepSeek V3.2 artık
aktif değildir; Qwen3 32B yalnızca acil durum teknik yedeğidir ve normal
arayüzde aktif bir Plan B olarak GÖSTERİLMEZ.
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

A2_PAGE_PATH = Path(__file__).resolve().parent.parent / "app_pages" / "a2_support_chatbot.py"

OLD_INACTIVE_MODEL_IDS = ["deepseek.v3.2", "moonshotai.kimi-k2.5"]


def test_a2_source_uses_gemma_defaults():
    source = A2_PAGE_PATH.read_text(encoding="utf-8")
    assert "google.gemma-4-31b" in source
    assert "qwen.qwen3-32b" in source  # yalnızca acil durum teknik yedek olarak


def test_a2_sidebar_default_env_gemma_only(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("A2_MODEL_A", raising=False)
    monkeypatch.setenv("A2_MODEL_B", "")
    monkeypatch.delenv("A2_FALLBACK_MODEL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/a2_support_chatbot.py")
    at.run(timeout=15)
    assert at.exception == []

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "google.gemma-4-31b" in technical_details_code
    for old_id in OLD_INACTIVE_MODEL_IDS:
        assert old_id not in technical_details_code

    captions = [c.value for c in at.sidebar.get("caption")]
    assert any("İkinci doğrulanmış Gemma modeli bulunmadığı" in c for c in captions)


def test_a2_sidebar_shows_second_plan_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A2_MODEL_A", "google.gemma-4-31b")
    monkeypatch.setenv("A2_MODEL_B", "google.gemma-4-26b-a4b")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/a2_support_chatbot.py")
    at.run(timeout=15)
    assert at.exception == []

    sidebar_markdown = "\n".join(m.value for m in at.sidebar.get("markdown"))
    assert "Gemma Plan B" in sidebar_markdown
    assert "Gemma 4 26B-A4B" in sidebar_markdown


def test_a2_fallback_never_shown_as_active_plan(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A2_MODEL_B", "")
    monkeypatch.setenv("A2_FALLBACK_MODEL", "qwen.qwen3-32b")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)

    at = AppTest.from_file("app_pages/a2_support_chatbot.py")
    at.run(timeout=15)
    assert at.exception == []

    sidebar_markdown = "\n".join(m.value for m in at.sidebar.get("markdown"))
    assert "Gemma Plan B" not in sidebar_markdown

    technical_details_code = "\n".join(c.value for c in at.sidebar.get("code"))
    assert "qwen.qwen3-32b" in technical_details_code
    assert "acil durum teknik yedek" in technical_details_code.lower() or "fallback" in technical_details_code.lower()


def test_a2_single_gemma_question_flow_does_not_call_second_model(monkeypatch, tmp_path):
    """A2_MODEL_B yapılandırılmamışken bir soru sorulduğunda yalnızca TEK
    model çağrılmalı (Plan B çağrısı hiç yapılmamalı)."""
    import copy

    from services.bedrock_client import ModelCallResult
    from services.evaluation_logger import log_evaluation as real_log_evaluation

    call_log = []

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens):
        call_log.append(model_id)
        return ModelCallResult(
            model_id=model_id,
            raw_text='{"answer": "test", "source_ids": [], "support_reason": "ok", "needs_escalation": false}',
            parsed_json={
                "answer": "test",
                "source_ids": [],
                "support_reason": "ok",
                "needs_escalation": False,
            },
            success=True,
            api_call_success=True,
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
            latency_ms=50.0,
        )

    csv_path = tmp_path / "evaluations.csv"

    def fake_log_evaluation(*args, **kwargs):
        kwargs["csv_path"] = csv_path
        return real_log_evaluation(*args, **kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("A2_MODEL_A", "test-gemma-a")
    # Boş string olarak ayarlanır (delenv değil) — aksi halde gerçek .env
    # dosyası load_dotenv() ile A2_MODEL_B'yi yeniden enjekte edebilir
    # (python-dotenv, zaten os.environ'da bulunan bir anahtarın üzerine
    # varsayılan olarak yazmaz; boş string de "bulunan" sayılır).
    monkeypatch.setenv("A2_MODEL_B", "")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    monkeypatch.setattr("services.a2_chat_service.call_model", fake_call_model)
    monkeypatch.setattr("services.evaluation_logger.log_evaluation", fake_log_evaluation)

    at = AppTest.from_file("app_pages/a2_support_chatbot.py")
    at.run(timeout=15)
    assert at.exception == []

    sample_btn = next(b for b in at.get("button") if b.key == "a2_sample_0")
    sample_btn.click().run(timeout=15)
    assert at.exception == []

    assert call_log == ["test-gemma-a"]
    turn = at.session_state["a2_chat_history"][0]
    assert turn["outcome_b"] is None
