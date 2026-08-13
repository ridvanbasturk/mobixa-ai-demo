"""B1 sayfasının uçtan uca üretim akışını, gerçek Bedrock çağrısı yapmadan
(services.bedrock_client.call_model sahtelenerek) Streamlit AppTest ile
test eder.

Bu testler, "Model A çalıştırılıyor..." spinner'ında sonsuza kadar takılma
sorununun kök nedenini (zaman aşımı olmadan bloklanan bir çağrı) düzelten
değişiklikleri doğrular: model hatası izolasyonu, generation_in_progress'in
her koşulda temizlenmesi, kısmi sonuçların korunması ve st.rerun sonrası
ödemeli çağrının tekrarlanmaması.

`log_evaluation` her testte geçici bir CSV dosyasına yönlendirilir; böylece
gerçek `outputs/evaluations.csv` dosyasına sahte test satırları yazılmaz.
"""
from __future__ import annotations

import copy

from streamlit.testing.v1 import AppTest

from services.bedrock_client import ModelCallResult
from services.evaluation_logger import log_evaluation as real_log_evaluation

VALID_B1_JSON = {
    "title": "Test Başlık",
    "questions": [
        {
            "question": "Soru 1?",
            "options": ["A", "B", "C", "D"],
            "correct_answer": 1,
            "explanation": "Açıklama",
            "source_quote": "Kaynak",
            "difficulty": "easy",
            "category": "Genel",
        }
    ],
    "learning_cards": [],
}


def _success_result(model_id: str) -> ModelCallResult:
    return ModelCallResult(
        model_id=model_id,
        raw_text="{...}",
        parsed_json=copy.deepcopy(VALID_B1_JSON),
        json_parse_method="json.loads",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=500.0,
        estimated_cost_usd=0.001,
        success=True,
        api_call_success=True,
    )


def _not_found_result(model_id: str) -> ModelCallResult:
    return ModelCallResult(
        model_id=model_id,
        error="Seçilen model Frankfurt Mantle kataloğunda bulunamadı.",
        error_category="not_found",
        api_call_success=False,
        success=False,
        latency_ms=50.0,
    )


def _find_radio(at, label_contains: str):
    return next(r for r in at.get("radio") if label_contains in r.label)


def _find_button(at, label: str):
    return next(b for b in at.get("button") if b.label == label)


def _patch_log_evaluation_to_tmp(monkeypatch, tmp_path) -> None:
    """log_evaluation çağrılarını gerçek outputs/evaluations.csv yerine geçici
    bir dosyaya yönlendirir; testler kalıcı CSV'yi kirletmez."""
    csv_path = tmp_path / "evaluations.csv"

    def fake_log_evaluation(*args, **kwargs):
        kwargs["csv_path"] = csv_path
        return real_log_evaluation(*args, **kwargs)

    monkeypatch.setattr("services.evaluation_logger.log_evaluation", fake_log_evaluation)


def _select_sample_content_and_prepare(at: AppTest) -> AppTest:
    at.run(timeout=15)
    _find_radio(at, "İçerik kaynağı").set_value("Hazır örnek metni kullan")
    # VALID_B1_JSON tam olarak 1 soru içerir ve learning_cards boştur; şema
    # doğrulamasının (soru sayısı eşleşmesi, öğrenme kartı gereksinimi)
    # başarılı sayılması için istenen soru sayısını 1 yapıp öğrenme kartı
    # talebini kapatıyoruz.
    next(n for n in at.get("number_input") if n.label == "Soru sayısı").set_value(1)
    next(c for c in at.get("checkbox") if c.label == "Öğrenme kartı oluştur").uncheck()
    at.run(timeout=15)
    return at


def _make_app_test(monkeypatch, tmp_path, call_recorder, model_a_result_fn, model_b_result_fn) -> AppTest:
    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens):
        call_recorder.append(model_id)
        if model_id == "test-model-a":
            return model_a_result_fn(model_id)
        return model_b_result_fn(model_id)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("B1_MODEL_A", "test-model-a")
    monkeypatch.setenv("B1_MODEL_B", "test-model-b")
    monkeypatch.setenv("TEXT_MODEL_A", "test-model-a")
    monkeypatch.setenv("TEXT_MODEL_B", "test-model-b")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    monkeypatch.setattr("services.bedrock_client.call_model", fake_call_model)
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/b1_content_generation.py")
    return _select_sample_content_and_prepare(at)


def test_model_a_failure_does_not_prevent_model_b_execution(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _not_found_result, _success_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)

    assert call_recorder == ["test-model-a", "test-model-b"]
    results = at.session_state["results"]
    assert results["a"]["call_result"].error_category == "not_found"
    assert results["b"]["call_result"].success is True
    assert at.exception == []


def test_generation_in_progress_cleared_after_success(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _success_result, _success_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)

    assert at.session_state["b1_generation_in_progress"] is False


def test_generation_in_progress_cleared_after_both_models_fail(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _not_found_result, _not_found_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)

    assert at.session_state["b1_generation_in_progress"] is False
    assert at.session_state["results"]["a"]["call_result"].success is False
    assert at.session_state["results"]["b"]["call_result"].success is False


def test_generation_in_progress_cleared_even_on_unexpected_exception(monkeypatch, tmp_path):
    call_recorder = []

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens):
        call_recorder.append(model_id)
        if model_id == "test-model-a":
            return _success_result(model_id)
        raise RuntimeError("beklenmeyen bir çökme (ör. disk dolu)")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("B1_MODEL_A", "test-model-a")
    monkeypatch.setenv("B1_MODEL_B", "test-model-b")
    monkeypatch.setenv("TEXT_MODEL_A", "test-model-a")
    monkeypatch.setenv("TEXT_MODEL_B", "test-model-b")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    monkeypatch.setattr("services.bedrock_client.call_model", fake_call_model)
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/b1_content_generation.py")
    at = _select_sample_content_and_prepare(at)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)

    # Beklenmeyen istisna script'i durdurur (at.exception dolu olur) ancak
    # finally bloğu yine de çalışmış olmalı.
    assert at.session_state["b1_generation_in_progress"] is False
    # Model A'nın sonucu, Model B çökmüş olsa bile kaybolmamalı (kısmi sonuç).
    assert at.session_state["results"]["a"] is not None
    assert at.session_state["results"]["a"]["call_result"].success is True
    assert at.session_state["results"]["b"] is None


def test_partial_results_preserved_across_rerun(monkeypatch, tmp_path):
    call_recorder = []

    def fake_call_model(model_id, system_prompt, user_prompt, temperature, max_tokens):
        call_recorder.append(model_id)
        if model_id == "test-model-a":
            return _success_result(model_id)
        raise RuntimeError("beklenmeyen bir çökme")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("B1_MODEL_A", "test-model-a")
    monkeypatch.setenv("B1_MODEL_B", "test-model-b")
    monkeypatch.setenv("TEXT_MODEL_A", "test-model-a")
    monkeypatch.setenv("TEXT_MODEL_B", "test-model-b")
    monkeypatch.setenv("INTER_MODEL_DELAY_SECONDS", "0")
    monkeypatch.setattr("services.bedrock_client.call_model", fake_call_model)
    _patch_log_evaluation_to_tmp(monkeypatch, tmp_path)

    at = AppTest.from_file("app_pages/b1_content_generation.py")
    at = _select_sample_content_and_prepare(at)
    _find_button(at, "İki Modelle Üret").click().run(timeout=15)

    # Bir sonraki (butona basılmayan) rerun'da da Model A'nın sonucu görünür kalmalı.
    at.run(timeout=15)
    assert at.session_state["results"]["a"] is not None
    assert at.session_state["results"]["a"]["call_result"].success is True


def test_no_repeated_invocation_after_rerun(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _success_result, _success_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)
    assert call_recorder == ["test-model-a", "test-model-b"]

    # Buton tekrar tıklanmadan yapılan ek rerun'lar ödemeli çağrıyı tekrarlamamalı.
    at.run(timeout=15)
    at.run(timeout=15)
    assert call_recorder == ["test-model-a", "test-model-b"]


def test_no_double_cost_after_rerun(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _success_result, _success_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)
    cost_after_generation = at.session_state["total_cost_usd"]
    assert cost_after_generation > 0

    at.run(timeout=15)
    at.run(timeout=15)
    assert at.session_state["total_cost_usd"] == cost_after_generation


def test_no_cost_added_for_failed_call(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _not_found_result, _not_found_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)
    assert at.session_state["total_cost_usd"] == 0.0


def test_one_model_failure_still_renders_both_cards_without_crashing(monkeypatch, tmp_path):
    call_recorder = []
    at = _make_app_test(monkeypatch, tmp_path, call_recorder, _not_found_result, _success_result)

    _find_button(at, "İki Modelle Üret").click().run(timeout=15)

    assert at.exception == []
    # Her iki sonuç da (biri hata, biri başarı) None olmadığından karşılaştırma
    # özeti ve her iki model kartı da render edilmiş olmalı.
    error_texts = " ".join(e.value for e in at.get("error"))
    success_texts = " ".join(s.value for s in at.get("success"))
    assert "Frankfurt Mantle kataloğunda bulunamadı" in error_texts
    assert "Başarılı" in success_texts
