"""Tüm modüllerde tekrar eden ortak UI metinleri (sidebar, metrik etiketleri,
bağlantı durumu, karşılaştırma özeti çerçevesi, genel butonlar)."""
from __future__ import annotations

TR = {
    "app.title": "Mobixa AI Demo",
    "common.sidebar_title": "Ayarlar",
    "common.region_label": "Bölge",
    "common.comparison_note": (
        "Karşılaştırma amaçlıdır; bir sağlayıcının otomatik olarak daha iyi "
        "olduğu anlamına gelmez."
    ),
    "common.technical_details": "Teknik detaylar",
    "common.temperature_label": "Sıcaklık (Temperature)",
    "common.max_tokens_label": "Maksimum çıktı token sayısı",
    "common.session_cost_label": "Oturumun tahmini toplam maliyeti:",
    "common.reset_cost_button": "Oturum maliyetini sıfırla",
    "common.download_csv_button": "Test kayıtlarını CSV indir",
    "common.pricing_caption": (
        "Fiyatlar Temmuz 2026 us-east-1 Standard fiyatlarına dayalı tahmini "
        "değerlerdir, gerçek faturalandırma AWS tarafından belirlenir."
    ),
    "common.metric.input_tokens": "Girdi token",
    "common.metric.output_tokens": "Çıktı token",
    "common.metric.total_tokens": "Toplam token",
    "common.metric.latency": "Gecikme (sn)",
    "common.metric.cost": "Tahmini maliyet",
    "common.value.none": "Yok",
    "common.value.not_calculated": "Hesaplanamadı",
    "common.status.success": "Başarılı",
    "common.status.failed": "Başarısız",
    "common.status.json_received_schema_failed": "JSON alındı ancak şema doğrulaması başarısız",
    "common.json_valid_label": "JSON geçerli mi:",
    "common.yes": "Evet",
    "common.no": "Hayır",
    "common.pydantic_label": "Pydantic doğrulama:",
    "common.status.passed": "Geçti",
    "common.validation_error_expander": "Doğrulama hatası detayı",
    "common.raw_output_expander": "Ham çıktı",
    "common.download_json_button": "JSON indir",
    "common.configured_model_caption": "Yapılandırılmış model: {name}",
    "common.comparison_title": "Karşılaştırma Özeti",
    "common.comparison_caption": (
        "Yalnızca bu çalıştırmadan elde edilen ölçülebilir teknik verilere "
        "dayanır. Anlamsal bir kalite yargısı değildir."
    ),
    "common.api_key_missing_error": (
        "API anahtarı bulunamadı. Lütfen .env dosyasında OPENAI_API_KEY tanımlayın."
    ),
    "common.raw_text_language_note": (
        "Not: Bu ham çıktı/hata metni şu an yalnızca Türkçe gösteriliyor "
        "(iç doğrulama katmanları henüz çok dilli değil)."
    ),
    "common.connection.no_key": "Bedrock yapılandırması eksik",
    "common.connection.untested": "API anahtarı bulundu — bağlantı henüz test edilmedi",
    "common.connection.success": "Bedrock bağlantısı başarılı",
    "common.connection.error": "Bedrock bağlantı hatası",
    "common.comparison.cost_none": "Maliyet karşılaştırması: Hiçbir model için ölçülemedi.",
    "common.comparison.cost_winner_prefix": "Bu çalıştırmada maliyet lideri: ",
    "common.comparison.cost_tie_prefix": "Maliyet eşitliği: ",
    "common.comparison.latency_none": "Gecikme karşılaştırması: Hiçbir model için ölçülemedi.",
    "common.comparison.latency_winner_prefix": "En hızlı model: ",
    "common.comparison.latency_tie_prefix": "Gecikme eşitliği: ",
    "common.comparison.tokens_none": "Token kullanımı karşılaştırması: Hiçbir model için ölçülemedi.",
    "common.comparison.tokens_winner_prefix": "En düşük token kullanımı: ",
    "common.comparison.tokens_tie_prefix": "Token kullanımı eşitliği: ",
    "common.comparison.both_json_schema_passed": "Her iki model de JSON ve şema doğrulamasını geçti.",
    "common.comparison.json_schema_line": "{label}: JSON ayrıştırma {json_status}, şema doğrulaması {schema_status}.",
    "common.comparison.status_passed": "geçti",
    "common.comparison.status_failed": "başarısız",
    "common.comparison.both_business_passed": "Her iki model de deterministik doğrulamayı geçti.",
    "common.comparison.business_line": "{label}: deterministik doğrulama {status}.",
    "common.comparison.and_join": " ve ",
}

EN = {
    "app.title": "Mobixa AI Demo",
    "common.sidebar_title": "Settings",
    "common.region_label": "Region",
    "common.comparison_note": (
        "For comparison purposes only; does not imply either provider is "
        "automatically better."
    ),
    "common.technical_details": "Technical details",
    "common.temperature_label": "Temperature",
    "common.max_tokens_label": "Maximum output token count",
    "common.session_cost_label": "Estimated total session cost:",
    "common.reset_cost_button": "Reset session cost",
    "common.download_csv_button": "Download test records CSV",
    "common.pricing_caption": (
        "Prices are estimates based on July 2026 us-east-1 Standard "
        "pricing; actual billing is determined by AWS."
    ),
    "common.metric.input_tokens": "Input tokens",
    "common.metric.output_tokens": "Output tokens",
    "common.metric.total_tokens": "Total tokens",
    "common.metric.latency": "Latency (s)",
    "common.metric.cost": "Estimated cost",
    "common.value.none": "N/A",
    "common.value.not_calculated": "Not calculated",
    "common.status.success": "Successful",
    "common.status.failed": "Failed",
    "common.status.json_received_schema_failed": "JSON received but schema validation failed",
    "common.json_valid_label": "JSON valid:",
    "common.yes": "Yes",
    "common.no": "No",
    "common.pydantic_label": "Pydantic validation:",
    "common.status.passed": "Passed",
    "common.validation_error_expander": "Validation error detail",
    "common.raw_output_expander": "Raw output",
    "common.download_json_button": "Download JSON",
    "common.configured_model_caption": "Configured model: {name}",
    "common.comparison_title": "Comparison Summary",
    "common.comparison_caption": (
        "Based only on measurable technical data from this run. Not a "
        "semantic quality judgment."
    ),
    "common.api_key_missing_error": (
        "API key not found. Please set OPENAI_API_KEY in your .env file."
    ),
    "common.raw_text_language_note": (
        "Note: this raw output/error text is currently shown in Turkish "
        "only (internal validation layers are not yet multilingual)."
    ),
    "common.connection.no_key": "Bedrock configuration is missing",
    "common.connection.untested": "API key found — connection not tested yet",
    "common.connection.success": "Bedrock connection successful",
    "common.connection.error": "Bedrock connection error",
    "common.comparison.cost_none": "Cost comparison: Could not be measured for either model.",
    "common.comparison.cost_winner_prefix": "Cost leader in this run: ",
    "common.comparison.cost_tie_prefix": "Cost tie: ",
    "common.comparison.latency_none": "Latency comparison: Could not be measured for either model.",
    "common.comparison.latency_winner_prefix": "Fastest model: ",
    "common.comparison.latency_tie_prefix": "Latency tie: ",
    "common.comparison.tokens_none": "Token usage comparison: Could not be measured for either model.",
    "common.comparison.tokens_winner_prefix": "Lowest token usage: ",
    "common.comparison.tokens_tie_prefix": "Token usage tie: ",
    "common.comparison.both_json_schema_passed": "Both models passed JSON and schema validation.",
    "common.comparison.json_schema_line": "{label}: JSON parsing {json_status}, schema validation {schema_status}.",
    "common.comparison.status_passed": "passed",
    "common.comparison.status_failed": "failed",
    "common.comparison.both_business_passed": "Both models passed deterministic validation.",
    "common.comparison.business_line": "{label}: deterministic validation {status}.",
    "common.comparison.and_join": " and ",
}
