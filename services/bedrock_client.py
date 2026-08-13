"""OpenAI uyumlu Amazon Bedrock Mantle endpoint istemcisi."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, urlunparse

from services.cost_calculator import estimate_cost_usd
from services.json_parser import parse_model_json
from services.model_registry import (
    MANTLE_ROUTE_OPENAI,
    MANTLE_ROUTE_STANDARD,
    resolve_model_route,
)

DEFAULT_BASE_URL = "https://bedrock-mantle.us-east-1.api.aws/v1"

# Yalnızca override amaçlı, isteğe bağlı ortam değişkeni. Ayarlanmışsa
# "openai" rotasına yönlendirilen modeller (ör. Gemma) için doğrudan bu
# base_url kullanılır; ayarlanmamışsa standart OPENAI_BASE_URL'den (URL
# ayrıştırmasıyla, saf metin değiştirme YAPILMADAN) türetilir. Kullanıcının
# bunu elle tanımlaması GEREKMEZ.
GEMMA_BASE_URL_OVERRIDE_ENV = "OPENAI_BASE_URL_GEMMA"

# Bir model çağrısının Streamlit sayfasını süresiz olarak bloke etmemesi için
# varsayılan bağlantı/istek zaman aşımları. Sır (secret) değildir; ortam
# değişkenleriyle geçersiz kılınabilir. OpenAI SDK'nın kendi varsayılanı
# (connect=5s, read=600s, max_retries=2) bilinen bir modelin dakikalarca
# yanıt vermeden beklemesine izin verdiği için buradaki değerler bilinçli
# olarak çok daha kısa tutulur.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_RETRIES = 0

# OPENAI_BASE_URL'den gerçek bölgeyi çıkarmak için kullanılan desen, ör.
# "https://bedrock-mantle.eu-central-1.api.aws/v1" -> "eu-central-1".
_ENDPOINT_REGION_PATTERN = re.compile(r"bedrock-mantle\.([a-z0-9-]+)\.api\.aws")

# Bazı hata mesajlarında bölge kodu yerine daha okunur bir şehir adı
# gösterilir (yalnızca kullanıcıya dönük metin içindir).
_REGION_DISPLAY_NAMES = {
    "eu-central-1": "Frankfurt",
    "us-east-1": "N. Virginia",
}


@dataclass
class ModelCallResult:
    model_id: str
    raw_text: Optional[str] = None
    parsed_json: Optional[dict] = None
    json_parse_method: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    estimated_cost_usd: Optional[float] = None
    success: bool = False
    error: Optional[str] = None
    # API çağrısının kendisinin (JSON ayrıştırmadan bağımsız olarak) başarılı
    # olup olmadığı — bağlantı durumu göstergesi için kullanılır.
    api_call_success: bool = False
    # "auth", "permission", "connection", "rate_limit", "timeout",
    # "not_found", "server_error", "api", "unknown"
    error_category: Optional[str] = None


def is_api_key_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


CONNECTION_STATUS_NO_KEY = "no_key"
CONNECTION_STATUS_UNTESTED = "untested"
CONNECTION_STATUS_SUCCESS = "success"
CONNECTION_STATUS_ERROR = "error"

_CONNECTION_ERROR_CATEGORIES = {"auth", "connection"}

# Sidebar'da gösterilecek (streamlit-seviyesi, "success"/"warning"/"error") ve
# mesaj metni çiftleri. Tüm sayfalar (B1, B6, ...) aynı bağlantı durumu
# göstergesini kullanır.
# Streamlit render seviyesi (değişmez, dilden bağımsız) + i18n anahtarı.
# Mesaj metninin kendisi services/i18n_strings/common.py içinde TR/EN olarak
# tutulur; sayfalar `t(CONNECTION_MESSAGE_KEYS[status])` ile okur.
CONNECTION_STATUS_LEVELS = {
    CONNECTION_STATUS_NO_KEY: "error",
    CONNECTION_STATUS_UNTESTED: "warning",
    CONNECTION_STATUS_SUCCESS: "success",
    CONNECTION_STATUS_ERROR: "error",
}

CONNECTION_MESSAGE_KEYS = {
    CONNECTION_STATUS_NO_KEY: "common.connection.no_key",
    CONNECTION_STATUS_UNTESTED: "common.connection.untested",
    CONNECTION_STATUS_SUCCESS: "common.connection.success",
    CONNECTION_STATUS_ERROR: "common.connection.error",
}


def next_connection_status(current_status: str, result: "ModelCallResult") -> str:
    """Bir model çağrısı sonucuna göre bağlantı durumunu günceller.

    - API çağrısı başarılıysa (JSON ayrıştırma sonucundan bağımsız) durum
      "success" olur.
    - Hata kimlik doğrulama veya bağlantı kaynaklıysa durum "error" olur.
    - Diğer hatalar (rate limit, timeout, yetki, sunucu hatası vb.)
      bağlantının kendisi hakkında kesin bilgi vermez; mevcut durum korunur.
    """
    if result.api_call_success:
        return CONNECTION_STATUS_SUCCESS
    if result.error_category in _CONNECTION_ERROR_CATEGORIES:
        return CONNECTION_STATUS_ERROR
    return current_status


def get_timeout_config() -> tuple[float, float]:
    """(connect_timeout_seconds, request_timeout_seconds) döner.

    BEDROCK_CONNECT_TIMEOUT_SECONDS / BEDROCK_REQUEST_TIMEOUT_SECONDS ortam
    değişkenleriyle geçersiz kılınabilir; sır içermez.
    """
    connect = float(os.environ.get("BEDROCK_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS))
    request = float(os.environ.get("BEDROCK_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS))
    return connect, request


def get_max_retries() -> int:
    """BEDROCK_MAX_RETRIES ortam değişkeninden yeniden deneme sayısını okur."""
    return int(os.environ.get("BEDROCK_MAX_RETRIES", DEFAULT_MAX_RETRIES))


def get_endpoint_host(base_url: Optional[str] = None) -> str:
    """OPENAI_BASE_URL'in gerçek host kısmını döner (teşhis amaçlı, sır içermez)."""
    url = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    try:
        host = urlparse(url).netloc
        return host or "(bilinmiyor)"
    except ValueError:
        return "(bilinmiyor)"


def get_endpoint_region(base_url: Optional[str] = None) -> str:
    """Gerçek bölgeyi OPENAI_BASE_URL'den çıkarır; ayrıştırılamazsa AWS_REGION'a düşer.

    Bu, sidebar'da gösterilen bölgenin gerçek uç noktayla (ör. eu-central-1
    yerine yanlışlıkla us-east-1 kalmış bir AWS_REGION değişkeni) tutarsız
    kalmasını önler.
    """
    url = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    match = _ENDPOINT_REGION_PATTERN.search(url)
    if match:
        return match.group(1)
    return os.environ.get("AWS_REGION", "us-east-1")


def region_display_name(region: str) -> str:
    """Bölge koduna karşılık gelen okunur şehir adını (varsa) döner."""
    return _REGION_DISPLAY_NAMES.get(region, region)


@dataclass
class DiagnosticInfo:
    """Güvenli (API anahtarı, prompt içeriği, yetkilendirme başlığı veya
    imzalı istek İÇERMEYEN) teşhis bilgisi. Yalnızca bağlantı testi ve
    teknik detaylar panelinde gösterilir."""

    endpoint_host: str
    endpoint_path: str
    region: str
    model_id: str
    key_configured: bool
    connect_timeout_seconds: float
    request_timeout_seconds: float
    max_retries: int
    mantle_route: str = MANTLE_ROUTE_STANDARD


def build_diagnostic_info(model_id: str) -> DiagnosticInfo:
    """Model çağrısına ait güvenli teşhis bilgisini toplar (API anahtarını asla döndürmez).

    model_id'nin çözümlendiği Mantle ROTASINA (standard/openai) göre gerçek
    base_url'i (dolayısıyla endpoint_host/endpoint_path/region) yansıtır —
    ör. Gemma modelleri için burada "/openai/v1" gösterilir, Qwen modelleri
    için "/v1" değişmeden görünür.
    """
    connect_timeout, request_timeout = get_timeout_config()
    route_info = resolve_model_route(model_id)
    base_url = get_base_url_for_route(route_info.mantle_route)
    return DiagnosticInfo(
        endpoint_host=get_endpoint_host(base_url),
        endpoint_path=urlparse(base_url).path or "/",
        region=get_endpoint_region(base_url),
        model_id=model_id,
        key_configured=is_api_key_configured(),
        connect_timeout_seconds=connect_timeout,
        request_timeout_seconds=request_timeout,
        max_retries=get_max_retries(),
        mantle_route=route_info.mantle_route,
    )


def get_client():
    """OpenAI SDK istemcisini environment değişkenlerinden oluşturur.

    API anahtarı yoksa None döner; anahtar asla loglanmaz. Bir modelin
    yanıt vermemesi durumunda Streamlit sayfasının süresiz beklememesi için
    açık bağlantı/istek zaman aşımları ve sınırlı yeniden deneme sayısı
    kullanılır (OpenAI SDK'nın kendi varsayılanı: connect=5s, read=600s,
    max_retries=2 — bu, yavaş/yanıt vermeyen bir model için dakikalarca
    sürebilir).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI, Timeout

    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    connect_timeout, request_timeout = get_timeout_config()
    timeout = Timeout(request_timeout, connect=connect_timeout)
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=get_max_retries())


# --- Model-bilinçli (model-aware) rota seçimi --------------------------------
#
# services/model_registry.py::resolve_model_route bir model_id için hangi
# Mantle ROTASININ (standard/openai) kullanılması gerektiğini söyler; bu
# bölüm o rotayı gerçek bir base_url'e çevirir ve rotaya göre önbelleklenmiş
# bir OpenAI istemcisi kurar. Mevcut OPENAI_BASE_URL davranışı (standart
# rota) HİÇBİR ŞEKİLDE değişmez — yalnızca "openai" rotasına çözümlenen
# modeller (ör. google.gemma-4-31b) farklı bir base_url kullanır.


def _derive_openai_route_base_url(standard_base_url: str) -> str:
    """Standart base_url'den ("... /v1") OpenAI-uyumlu Mantle rotasının
    base_url'ini ("... /openai/v1") TÜRETIR.

    Saf metin değiştirme (ör. ".replace('/v1', '/openai/v1')") KULLANMAZ —
    bu, "/v1" alt dizesi başka bir yerde (ör. host adında) geçerse hatalı
    bir yol üretebilir. Bunun yerine urlparse ile yol (path) parçalanır,
    "openai" segmenti başta değilse eklenir; şema/host/bölge dokunulmadan
    korunur. İşlem idempotenttir: zaten "/openai/..." olan bir yol
    değişmeden döner.

    Örnekler:
      ".../v1"        -> ".../openai/v1"
      ".../openai/v1" -> ".../openai/v1"  (değişmez)
      "..." (yol yok) -> ".../openai/v1"
    """
    try:
        parsed = urlparse(standard_base_url)
    except ValueError:
        # Ayrıştırılamayan bir URL için son çare: sona güvenli bir şekilde ekle.
        cleaned = standard_base_url.rstrip("/")
        return f"{cleaned}/openai/v1"

    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    if segments and segments[0] == "openai":
        new_segments = segments
    elif segments:
        new_segments = ["openai"] + segments
    else:
        new_segments = ["openai", "v1"]

    new_path = "/" + "/".join(new_segments)
    return urlunparse(parsed._replace(path=new_path))


def get_base_url_for_route(mantle_route: str) -> str:
    """Verilen Mantle rota türü ("standard" veya "openai") için kullanılacak
    base_url'i döner.

    - "standard": mevcut OPENAI_BASE_URL (veya varsayılan) — DEĞİŞMEZ.
    - "openai": önce OPENAI_BASE_URL_GEMMA override'ı kontrol edilir; o
      ayarlı değilse standart base_url'den urlparse ile güvenli biçimde
      türetilir. Global OPENAI_BASE_URL ortam değişkeni HİÇBİR KOŞULDA
      çalışma zamanında değiştirilmez.
    - bilinmeyen bir rota türü verilirse (beklenmez) standart base_url'e
      güvenli biçimde geri düşülür.
    """
    standard_base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    if mantle_route == MANTLE_ROUTE_OPENAI:
        override = os.environ.get(GEMMA_BASE_URL_OVERRIDE_ENV)
        if override:
            return override
        return _derive_openai_route_base_url(standard_base_url)
    return standard_base_url


# (base_url, connect_timeout, request_timeout, max_retries) -> OpenAI istemcisi.
# API anahtarının KENDİSİ önbellek anahtarına dahil edilmez (loglanmaz/
# görünür durumda tutulmaz); anahtar zaten süreç ömrü boyunca .env'den bir
# kez okunur ve değişmesi beklenmez.
_client_cache: Dict[Tuple[str, float, float, int], object] = {}


def clear_client_cache() -> None:
    """İstemci önbelleğini temizler. Yalnızca testlerde (farklı sahte
    API anahtarları/base_url'ler arasında sızıntıyı önlemek için) veya
    ortam değişkenleri çalışma zamanında bilinçli olarak değiştirildiğinde
    kullanılır; normal uygulama akışında çağrılması gerekmez."""
    _client_cache.clear()


def get_client_for_model(model_id: str):
    """Verilen model_id için doğru Mantle rotasına yönlendirilmiş, önbelleklenmiş
    bir OpenAI istemcisi döner.

    Adımlar: (1) model_registry.resolve_model_route ile rota metadatasını
    çözer, (2) get_base_url_for_route ile gerçek base_url'i belirler,
    (3) aynı (base_url, zaman aşımı, yeniden deneme) kombinasyonu için
    daha önce oluşturulmuş bir istemci varsa onu yeniden kullanır, yoksa
    yenisini oluşturup önbelleğe alır. API anahtarı yoksa None döner;
    anahtar hiçbir koşulda loglanmaz veya döndürülen nesne dışında saklanmaz.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    route_info = resolve_model_route(model_id)
    base_url = get_base_url_for_route(route_info.mantle_route)
    connect_timeout, request_timeout = get_timeout_config()
    max_retries = get_max_retries()

    cache_key = (base_url, connect_timeout, request_timeout, max_retries)
    cached = _client_cache.get(cache_key)
    if cached is not None:
        return cached

    from openai import OpenAI, Timeout

    timeout = Timeout(request_timeout, connect=connect_timeout)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
    _client_cache[cache_key] = client
    return client


# Bedrock Mantle'ın, bir modelin çağrıldığı rotada desteklenmediğini
# belirtirken kullandığı, doğrulanmış hata mesajı alt dizesi (bkz. proje
# geçmişi: google.gemma-4-31b + standart /v1 rotası).
_ROUTE_UNSUPPORTED_MARKER = "isn't supported on this route"

# Doğrulanmış kök neden: bazı modeller (ör. belirli bir Gemma "thinking"
# varyantı) yalnızca varsayılan `temperature` değerini (1) kabul eder;
# açıkça farklı bir değer gönderilirse HTTP 400 ile reddedilir:
# "Unsupported value: 'temperature' does not support 0.2 with this
# model. Only the default (1) value is supported." Bu, max_tokens
# hatasından FARKLI bir modeldir (rotaya değil, modele özgü olabilir) —
# bu yüzden rota metadatasına değil, hatanın kendisine bakılarak tespit
# edilir ve yalnızca bu durumda `temperature` parametresi tamamen
# atlanarak (API'nin kendi varsayılanını kullanmasına izin verilerek)
# TEK SEFER yeniden denenir.
_FIXED_TEMPERATURE_PARAM = "temperature"


def _is_fixed_temperature_error(exc: Exception) -> bool:
    try:
        import openai

        if not isinstance(exc, openai.APIStatusError) or exc.status_code != 400:
            return False
        body = getattr(exc, "body", None)
        param = None
        if isinstance(body, dict):
            param = (body.get("error") or {}).get("param")
        if param == _FIXED_TEMPERATURE_PARAM:
            return True
        message = exc.message or ""
        return (
            f"'{_FIXED_TEMPERATURE_PARAM}'" in message
            and "Only the default" in message
        )
    except ImportError:
        return False


def _classify_error(exc: Exception) -> tuple[str, str]:
    """OpenAI SDK istisnalarını anlaşılır Türkçe mesaja ve kısa kategoriye çevirir."""
    try:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return (
                "Kimlik doğrulama başarısız. Short-term API anahtarının süresi dolmuş "
                "veya yanlış bölge için üretilmiş olabilir.",
                "auth",
            )
        if isinstance(exc, openai.PermissionDeniedError):
            return "Bu model veya işlem için AWS yetkisi bulunmuyor.", "permission"
        if isinstance(exc, openai.RateLimitError):
            return "İstek sınırına ulaşıldı. Kısa süre sonra yeniden deneyin.", "rate_limit"
        if isinstance(exc, openai.APITimeoutError):
            _, request_timeout = get_timeout_config()
            return (
                f"Model çağrısı {int(request_timeout)} saniye içinde tamamlanmadı ve "
                "güvenli biçimde durduruldu.",
                "timeout",
            )
        if isinstance(exc, openai.NotFoundError):
            region_name = region_display_name(get_endpoint_region())
            return f"Seçilen model {region_name} Mantle kataloğunda bulunamadı.", "not_found"
        if isinstance(exc, openai.APIConnectionError):
            return "Bağlantı hatası: Bedrock uç noktasına ulaşılamadı.", "connection"
        if isinstance(exc, openai.InternalServerError):
            return (
                "Bedrock tarafında geçici bir sunucu hatası oluştu (5xx). Lütfen tekrar deneyin.",
                "server_error",
            )
        if isinstance(exc, openai.APIStatusError):
            if exc.status_code == 408:
                return (
                    "Model çağrısı sunucu tarafında zaman aşımına uğradı (HTTP 408).",
                    "timeout",
                )
            if exc.status_code == 400 and _ROUTE_UNSUPPORTED_MARKER in (exc.message or ""):
                # Kök neden doğrulandı: bazı modeller (ör. google.gemma-4-31b)
                # standart /v1 rotasında değil, yalnızca get_client_for_model'in
                # yönlendirdiği "openai" rotasında (/openai/v1) çalışır. Bu hata
                # normalde model_registry doğru yapılandırıldığında hiç
                # oluşmamalıdır; oluşursa kayıt dışı bırakılmış bir model
                # olduğuna işaret eder.
                return (
                    "Seçilen model bu Mantle API rotasında desteklenmiyor.",
                    "route_not_supported",
                )
            return f"API hatası (HTTP {exc.status_code}): {exc.message}", "api"
        if isinstance(exc, openai.APIError):
            return f"Genel API hatası: {exc}", "api"
    except ImportError:
        pass
    return f"Beklenmeyen hata: {exc}", "unknown"


def call_model(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/png",
) -> ModelCallResult:
    """Bedrock Mantle üzerinden tek bir model çağrısı yapar.

    Bir modelin başarısız olması diğer modelin çağrısını etkilemez;
    hatalar burada yakalanıp ModelCallResult içinde döndürülür. Çağrı,
    `get_client()` tarafından ayarlanan açık zaman aşımları sayesinde
    süresiz olarak beklemez.

    `image_bytes` verilirse (A1 AI Görsel Analiz Modu gibi çok-modlu
    kullanımlar için) kullanıcı mesajı metin + görsel (data URL) içeren bir
    içerik listesine dönüşür; verilmezse davranış tamamen eskisiyle
    aynıdır (yalnızca metin). Görsel baytları hiçbir koşulda loglanmaz.
    """
    result = ModelCallResult(model_id=model_id)

    # Model-bilinçli rota seçimi: çoğu model (Qwen dahil) standart /v1
    # rotasını kullanmaya devam eder; yalnızca model_registry'de "openai"
    # rotasına çözümlenen modeller (ör. google.gemma-4-31b) farklı bir
    # base_url'e yönlendirilir. Bkz. get_client_for_model.
    client = get_client_for_model(model_id)
    if client is None:
        result.error = "API anahtarı bulunamadı. Lütfen .env dosyasında OPENAI_API_KEY tanımlayın."
        result.error_category = "auth"
        return result

    if image_bytes is not None:
        import base64

        encoded = base64.b64encode(image_bytes).decode("ascii")
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{encoded}"}},
        ]
    else:
        user_content = user_prompt

    # Doğrulanmış kök neden: "openai" rotasına yönlendirilen modeller (ör.
    # google.gemma-4-31b) klasik `max_tokens` parametresini KABUL ETMEZ —
    # "Unsupported parameter: 'max_tokens' is not supported with this
    # model." (HTTP 400) döner; yalnızca `max_completion_tokens` kabul
    # ederler. Standart /v1 rotasındaki modeller (Qwen dahil) hâlâ
    # `max_tokens` bekler; bu yüzden parametre adı rotaya göre seçilir.
    route_info = resolve_model_route(model_id)
    token_limit_kwargs = (
        {"max_completion_tokens": max_tokens}
        if route_info.mantle_route == MANTLE_ROUTE_OPENAI
        else {"max_tokens": max_tokens}
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            **token_limit_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - hataları sınıflandırıp kullanıcıya göster
        if _is_fixed_temperature_error(exc):
            try:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    **token_limit_kwargs,
                )
            except Exception as retry_exc:  # noqa: BLE001
                result.latency_ms = (time.perf_counter() - start) * 1000
                result.error, result.error_category = _classify_error(retry_exc)
                return result
        else:
            result.latency_ms = (time.perf_counter() - start) * 1000
            result.error, result.error_category = _classify_error(exc)
            return result

    result.latency_ms = (time.perf_counter() - start) * 1000

    try:
        result.raw_text = response.choices[0].message.content
    except (IndexError, AttributeError) as exc:
        result.error = f"Model yanıtı beklenen formatta değil: {exc}"
        result.error_category = "api"
        return result

    # API çağrısı ve yanıt ayrıştırma buraya kadar başarılı; JSON/şema
    # doğrulaması başarısız olsa bile bağlantının kendisi çalışıyor demektir.
    result.api_call_success = True

    usage = getattr(response, "usage", None)
    if usage is not None:
        result.input_tokens = getattr(usage, "prompt_tokens", None)
        result.output_tokens = getattr(usage, "completion_tokens", None)
        result.total_tokens = getattr(usage, "total_tokens", None)

    result.estimated_cost_usd = estimate_cost_usd(
        model_id, result.input_tokens, result.output_tokens
    )

    parse_result = parse_model_json(result.raw_text)
    result.parsed_json = parse_result.data
    result.json_parse_method = parse_result.method

    if not parse_result.success:
        result.error = parse_result.error or "JSON ayrıştırılamadı"
        result.success = False
        return result

    result.success = True
    return result
