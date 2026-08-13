import httpx
import openai
import pytest

import services.bedrock_client as bedrock_client
from services.bedrock_client import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    GEMMA_BASE_URL_OVERRIDE_ENV,
    _classify_error,
    _derive_openai_route_base_url,
    build_diagnostic_info,
    call_model,
    clear_client_cache,
    get_base_url_for_route,
    get_client_for_model,
    get_endpoint_host,
    get_endpoint_region,
    get_max_retries,
    get_timeout_config,
    region_display_name,
)
from services.model_registry import MANTLE_ROUTE_OPENAI, MANTLE_ROUTE_STANDARD

FAKE_REQUEST = httpx.Request("POST", "https://bedrock-mantle.eu-central-1.api.aws/v1/chat/completions")


@pytest.fixture(autouse=True)
def _isolated_client_cache():
    """Her test kendi istemci önbelleğiyle başlar/biter; farklı testlerin
    sahte OPENAI_API_KEY/base_url kombinasyonlarının birbirine sızmasını önler."""
    clear_client_cache()
    yield
    clear_client_cache()


def _status_error(cls, status_code: int, message: str = "hata"):
    response = httpx.Response(status_code, request=FAKE_REQUEST, json={"error": {"message": message}})
    return cls(message, response=response, body=None)


# --- Timeout/retry configuration -------------------------------------------


def test_default_timeout_config_used_when_env_unset(monkeypatch):
    monkeypatch.delenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("BEDROCK_REQUEST_TIMEOUT_SECONDS", raising=False)
    connect, request = get_timeout_config()
    assert connect == DEFAULT_CONNECT_TIMEOUT_SECONDS
    assert request == DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_timeout_config_overridden_by_env(monkeypatch):
    monkeypatch.setenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("BEDROCK_REQUEST_TIMEOUT_SECONDS", "20")
    connect, request = get_timeout_config()
    assert connect == 3.0
    assert request == 20.0


def test_default_max_retries_used_when_env_unset(monkeypatch):
    monkeypatch.delenv("BEDROCK_MAX_RETRIES", raising=False)
    assert get_max_retries() == DEFAULT_MAX_RETRIES


def test_max_retries_overridden_by_env(monkeypatch):
    monkeypatch.setenv("BEDROCK_MAX_RETRIES", "1")
    assert get_max_retries() == 1


def test_default_timeouts_are_bounded_not_the_sdk_default():
    # OpenAI SDK'nın kendi varsayılanı read=600s'dir; bu, bir modelin
    # dakikalarca yanıt vermeden Streamlit sayfasını kilitlemesine izin
    # verdiği için buradaki varsayılanlar kesinlikle daha kısa olmalı.
    assert DEFAULT_REQUEST_TIMEOUT_SECONDS < 600
    assert DEFAULT_CONNECT_TIMEOUT_SECONDS < 600


# --- Endpoint/region derivation ---------------------------------------------


def test_region_derived_from_frankfurt_endpoint():
    assert get_endpoint_region("https://bedrock-mantle.eu-central-1.api.aws/v1") == "eu-central-1"


def test_region_derived_from_us_east_endpoint():
    assert get_endpoint_region("https://bedrock-mantle.us-east-1.api.aws/v1") == "us-east-1"


def test_region_falls_back_to_aws_region_env_when_unparseable(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    assert get_endpoint_region("https://not-a-mantle-host.example.com") == "eu-west-1"


def test_endpoint_host_extracted():
    assert get_endpoint_host("https://bedrock-mantle.eu-central-1.api.aws/v1") == "bedrock-mantle.eu-central-1.api.aws"


def test_region_display_name_known_and_unknown():
    assert region_display_name("eu-central-1") == "Frankfurt"
    assert region_display_name("ap-southeast-2") == "ap-southeast-2"


# --- Safe diagnostics --------------------------------------------------------


def test_diagnostic_info_never_includes_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value-should-never-leak")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    info = build_diagnostic_info("qwen.qwen3-32b")

    dumped = str(info)
    assert "sk-super-secret-value-should-never-leak" not in dumped
    assert info.key_configured is True
    assert info.model_id == "qwen.qwen3-32b"
    assert info.region == "eu-central-1"


def test_diagnostic_info_reports_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    info = build_diagnostic_info("qwen.qwen3-32b")
    assert info.key_configured is False


# --- Error classification ----------------------------------------------------


def test_classify_authentication_error():
    exc = _status_error(openai.AuthenticationError, 401)
    message, category = _classify_error(exc)
    assert category == "auth"
    assert "Kimlik doğrulama" in message


def test_classify_permission_denied_error():
    exc = _status_error(openai.PermissionDeniedError, 403)
    message, category = _classify_error(exc)
    assert category == "permission"
    assert "yetkisi bulunmuyor" in message


def test_classify_not_found_error_mentions_frankfurt(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    exc = _status_error(openai.NotFoundError, 404)
    message, category = _classify_error(exc)
    assert category == "not_found"
    assert "Frankfurt" in message
    assert "bulunamadı" in message


def test_classify_rate_limit_error():
    exc = _status_error(openai.RateLimitError, 429)
    message, category = _classify_error(exc)
    assert category == "rate_limit"
    assert "İstek sınırına" in message


def test_classify_timeout_error(monkeypatch):
    monkeypatch.setenv("BEDROCK_REQUEST_TIMEOUT_SECONDS", "45")
    exc = openai.APITimeoutError(request=FAKE_REQUEST)
    message, category = _classify_error(exc)
    assert category == "timeout"
    assert "45 saniye" in message


def test_classify_connection_error():
    exc = openai.APIConnectionError(request=FAKE_REQUEST)
    message, category = _classify_error(exc)
    assert category == "connection"


def test_classify_internal_server_error():
    exc = _status_error(openai.InternalServerError, 500)
    message, category = _classify_error(exc)
    assert category == "server_error"
    assert "sunucu hatası" in message


def test_classify_generic_status_error_408_as_timeout():
    exc = _status_error(openai.APIStatusError, 408)
    message, category = _classify_error(exc)
    assert category == "timeout"


def test_classify_unknown_exception():
    message, category = _classify_error(ValueError("garip bir hata"))
    assert category == "unknown"


def test_classify_route_unsupported_error():
    exc = _status_error(
        openai.BadRequestError, 400, "model `google.gemma-4-31b` isn't supported on this route"
    )
    message, category = _classify_error(exc)
    assert category == "route_not_supported"
    assert message == "Seçilen model bu Mantle API rotasında desteklenmiyor."


def test_classify_generic_400_error_not_misclassified_as_route_error():
    exc = _status_error(openai.BadRequestError, 400, "invalid temperature value")
    message, category = _classify_error(exc)
    assert category == "api"


# --- Faz 4C(sonrası): model-bilinçli Mantle rota seçimi ----------------------


def test_route_derivation_from_standard_v1():
    assert (
        _derive_openai_route_base_url("https://bedrock-mantle.eu-central-1.api.aws/v1")
        == "https://bedrock-mantle.eu-central-1.api.aws/openai/v1"
    )


def test_route_derivation_idempotent_when_already_openai():
    assert (
        _derive_openai_route_base_url("https://bedrock-mantle.eu-central-1.api.aws/openai/v1")
        == "https://bedrock-mantle.eu-central-1.api.aws/openai/v1"
    )


def test_route_derivation_preserves_scheme_host_region():
    derived = _derive_openai_route_base_url("https://bedrock-mantle.us-east-1.api.aws/v1")
    assert derived.startswith("https://bedrock-mantle.us-east-1.api.aws/")
    assert derived.endswith("/openai/v1")


def test_route_derivation_handles_missing_path():
    derived = _derive_openai_route_base_url("https://bedrock-mantle.eu-central-1.api.aws")
    assert derived == "https://bedrock-mantle.eu-central-1.api.aws/openai/v1"


def test_route_derivation_does_not_use_naive_string_replace():
    # "/v1" alt dizesi host adında da geçse (uydurma örnek), path dışına
    # taşınmamalı — urlparse tabanlı olduğu için yalnızca path etkilenir.
    derived = _derive_openai_route_base_url("https://v1.bedrock-mantle.eu-central-1.api.aws/v1")
    assert derived == "https://v1.bedrock-mantle.eu-central-1.api.aws/openai/v1"


def test_get_base_url_for_route_standard_matches_global_env(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    assert get_base_url_for_route(MANTLE_ROUTE_STANDARD) == "https://bedrock-mantle.eu-central-1.api.aws/v1"


def test_get_base_url_for_route_openai_derives_from_standard(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.delenv(GEMMA_BASE_URL_OVERRIDE_ENV, raising=False)
    assert get_base_url_for_route(MANTLE_ROUTE_OPENAI) == "https://bedrock-mantle.eu-central-1.api.aws/openai/v1"


def test_get_base_url_for_route_openai_override_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.setenv(GEMMA_BASE_URL_OVERRIDE_ENV, "https://custom-gemma-route.example.com/openai/v1")
    assert get_base_url_for_route(MANTLE_ROUTE_OPENAI) == "https://custom-gemma-route.example.com/openai/v1"


def test_global_openai_base_url_env_value_unchanged_by_route_resolution(monkeypatch):
    # get_base_url_for_route/get_client_for_model, OPENAI_BASE_URL ortam
    # değişkenini ÇALIŞMA ZAMANINDA asla değiştirmemeli (yalnızca okur).
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    get_base_url_for_route(MANTLE_ROUTE_OPENAI)
    get_client_for_model("google.gemma-4-31b")
    import os

    assert os.environ["OPENAI_BASE_URL"] == "https://bedrock-mantle.eu-central-1.api.aws/v1"


def test_get_client_for_model_qwen_uses_standard_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    client = get_client_for_model("qwen.qwen3-235b-a22b-2507")
    assert client is not None
    assert str(client.base_url) == "https://bedrock-mantle.eu-central-1.api.aws/v1/"


def test_get_client_for_model_gemma_uses_openai_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.delenv(GEMMA_BASE_URL_OVERRIDE_ENV, raising=False)
    client = get_client_for_model("google.gemma-4-31b")
    assert client is not None
    assert str(client.base_url) == "https://bedrock-mantle.eu-central-1.api.aws/openai/v1/"


def test_get_client_for_model_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_client_for_model("google.gemma-4-31b") is None


def test_client_cache_separates_standard_and_openai_route_clients(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    qwen_client = get_client_for_model("qwen.qwen3-235b-a22b-2507")
    gemma_client = get_client_for_model("google.gemma-4-31b")
    assert qwen_client is not gemma_client
    assert str(qwen_client.base_url) != str(gemma_client.base_url)


def test_client_cache_reuses_client_for_same_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    first = get_client_for_model("qwen.qwen3-235b-a22b-2507")
    second = get_client_for_model("qwen.qwen3-32b")  # farklı model, aynı (standart) rota
    assert first is second


def test_client_cache_never_keyed_by_api_key_value(monkeypatch):
    # Aynı rota + zaman aşımı + yeniden deneme kombinasyonu, API anahtarı
    # farklı olsa bile (önbellek anahtarına anahtar DAHİL EDİLMEDİĞİ için)
    # aynı istemciyi döndürür — bu, belgelenen önbellekleme davranışıdır.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "first-fake-key")
    first = get_client_for_model("qwen.qwen3-235b-a22b-2507")
    monkeypatch.setenv("OPENAI_API_KEY", "second-fake-key")
    second = get_client_for_model("qwen.qwen3-235b-a22b-2507")
    assert first is second


def test_build_diagnostic_info_reflects_gemma_route(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    monkeypatch.delenv(GEMMA_BASE_URL_OVERRIDE_ENV, raising=False)
    info = build_diagnostic_info("google.gemma-4-31b")
    assert info.mantle_route == MANTLE_ROUTE_OPENAI
    assert info.endpoint_path == "/openai/v1"


def test_build_diagnostic_info_reflects_qwen_standard_route(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.eu-central-1.api.aws/v1")
    info = build_diagnostic_info("qwen.qwen3-235b-a22b-2507")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD
    assert info.endpoint_path == "/v1"


class _FakeCompletions:
    def __init__(self):
        self.received_kwargs = None

    def create(self, **kwargs):
        self.received_kwargs = kwargs
        raise RuntimeError("test stops here on purpose")


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


def test_call_model_uses_max_completion_tokens_for_openai_route(monkeypatch):
    # Doğrulanmış kök neden (bkz. bedrock_client.py yorumu): "openai"
    # rotasındaki modeller (ör. google.gemma-4-31b) klasik `max_tokens`
    # parametresini HTTP 400 ile reddeder, yalnızca `max_completion_tokens`
    # kabul ederler.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    fake_client = _FakeClient()
    monkeypatch.setattr(bedrock_client, "get_client_for_model", lambda model_id: fake_client)

    call_model("google.gemma-4-31b", "system", "user", temperature=0.2, max_tokens=1234)

    assert fake_client.chat.completions.received_kwargs["max_completion_tokens"] == 1234
    assert "max_tokens" not in fake_client.chat.completions.received_kwargs


def test_call_model_uses_max_tokens_for_standard_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    fake_client = _FakeClient()
    monkeypatch.setattr(bedrock_client, "get_client_for_model", lambda model_id: fake_client)

    call_model("qwen.qwen3-235b-a22b-2507", "system", "user", temperature=0.2, max_tokens=1234)

    assert fake_client.chat.completions.received_kwargs["max_tokens"] == 1234
    assert "max_completion_tokens" not in fake_client.chat.completions.received_kwargs


class _FakeResponse:
    def __init__(self, text: str):
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": text})()})]
        self.usage = None


class _FixedTemperatureCompletions:
    """İlk çağrıda 'temperature' 400 hatası fırlatır, ikinci (yeniden
    deneme) çağrıda başarılı bir yanıt döner ve gönderilen kwargs'ları
    her iki çağrı için de kaydeder."""

    def __init__(self, error_exc: Exception):
        self.error_exc = error_exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise self.error_exc
        return _FakeResponse('{"ok": true}')


def test_call_model_retries_without_temperature_on_fixed_temperature_error(monkeypatch):
    # Doğrulanmış kök neden: bazı modeller yalnızca varsayılan temperature
    # (1) değerini kabul eder, açık bir değer HTTP 400 ile reddedilir.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    error_exc = _status_error(
        openai.APIStatusError,
        400,
        "Unsupported value: 'temperature' does not support 0.2 with this model. "
        "Only the default (1) value is supported.",
    )
    fake_completions = _FixedTemperatureCompletions(error_exc)
    fake_client = type("C", (), {"chat": type("Chat", (), {"completions": fake_completions})()})()
    monkeypatch.setattr(bedrock_client, "get_client_for_model", lambda model_id: fake_client)

    result = call_model("google.gemma-4-31b", "system", "user", temperature=0.2, max_tokens=500)

    assert len(fake_completions.calls) == 2
    assert fake_completions.calls[0]["temperature"] == 0.2
    assert "temperature" not in fake_completions.calls[1]
    assert result.api_call_success is True
    assert result.error is None


def test_call_model_does_not_retry_on_unrelated_400_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    error_exc = _status_error(openai.APIStatusError, 400, "some other bad request")
    fake_completions = _FixedTemperatureCompletions(error_exc)
    fake_client = type("C", (), {"chat": type("Chat", (), {"completions": fake_completions})()})()
    monkeypatch.setattr(bedrock_client, "get_client_for_model", lambda model_id: fake_client)

    result = call_model("google.gemma-4-31b", "system", "user", temperature=0.2, max_tokens=500)

    assert len(fake_completions.calls) == 1
    assert result.api_call_success is False
    assert result.error is not None
