"""C1 (Otomatik Journey Oluşturma) modülüne özgü metinler."""
from __future__ import annotations

TR = {
    "c1.page_subtitle": "C1 — Otomatik Journey Oluşturma",
    "c1.page_caption": (
        "Journey talebi (hedef kitle, amaç, zorunlu konular) ve mevcut "
        "aktivite kataloğu kullanılarak düzenlenebilir bir Journey önerilir. "
        "Model yalnızca katalogdaki aktiviteleri seçebilir, yeni içerik "
        "üretmez."
    ),
    "c1.session_cost_caption": (
        "Bu tutar yalnızca mevcut oturumda yapılan başarılı model çağrılarını "
        "içerir (B1, B6 ve C1 dahil). Sıfırlamak CSV geçmişini etkilemez."
    ),
    "c1.section.data_selection": "1. Örnek/Yükleme Seçimi",
    "c1.data_source_label": "Veri kaynağı",
    "c1.data_source.sample": "Örnek veriyi kullan",
    "c1.data_source.upload": "Kendi dosyalarımı yükle",
    "c1.brief_uploader_label": "Journey talebi (JSON)",
    "c1.catalog_uploader_label": "Aktivite kataloğu (CSV)",
    "c1.info.upload_brief": "Lütfen bir Journey talebi JSON dosyası yükleyin.",
    "c1.info.upload_catalog": "Lütfen bir aktivite kataloğu CSV dosyası yükleyin.",
    "c1.section.brief_preview": "2. Journey Talebi Önizleme",
    "c1.info.provide_valid_brief": "Önizlemek için geçerli bir Journey talebi sağlayın.",
    "c1.section.catalog_preview": "3. Aktivite Kataloğu Önizleme",
    "c1.catalog_synthetic_note": (
        "Not: Başlığı '[Örnek Veri]' ile başlayan satırlar sentetik/"
        "illüstratif test verisidir, gerçek Mobixa sisteminden alınmadı "
        "— özellikle 'LEARN' (öğrenme kartı) tipi aktivitelerin gerçek "
        "şeması henüz paylaşılmadığı için bu satırlar tahminidir. "
        "Diğer tüm satırlar (id sayısal olanlar) yöneticinin paylaştığı "
        "gerçek aktivite JSON'larından türetilmiştir."
    ),
    "c1.info.provide_valid_catalog": "Önizlemek için geçerli bir aktivite kataloğu sağlayın.",
    "c1.warning.unknown_excluded": (
        "Brief'teki bazı hariç tutulacak aktivite kimlikleri katalogda bulunamadı: {ids}"
    ),
    "c1.section.brief_summary": "4. Journey Talebi Özeti",
    "c1.metric.min_activities": "Min. aktivite",
    "c1.metric.max_activities": "Maks. aktivite",
    "c1.metric.must_end_with_test": "Sınavla bitmeli mi",
    "c1.metric.required_topics_count": "Zorunlu konu sayısı",
    "c1.section.generation": "5. Üretim",
    "c1.generate_button": "İki Modelle Journey Üret",
    "c1.error.missing_data": "Lütfen önce geçerli bir Journey talebi ve aktivite kataloğu sağlayın.",
    "c1.spinner.model_a": "Model A çalıştırılıyor...",
    "c1.spinner.model_b": "Model B çalıştırılıyor...",
    "c1.section.results": "6-7. Model Sonuçları",
    "c1.info.click_to_generate": "Sonuçları görmek için önce 'İki Modelle Journey Üret' butonuna tıklayın.",
    "c1.configured_model_caption": "Yapılandırılmış model: {name}",
    "c1.business_check.passed": "İş kuralı doğrulaması: Geçti",
    "c1.business_check.failed": "İş kuralı doğrulaması: Başarısız — {errors}",
    "c1.business_check.warnings": "Uyarılar: {warnings}",
    "c1.business_check.topics_coverage": "Zorunlu konu kapsamı: {covered}/{total}",
    "c1.audience_fit_label": "Hedef kitle uygunluğu:",
    "c1.strategy_summary_label": "Strateji özeti:",
    "c1.total_minutes_label": "Toplam süre:",
    "c1.minutes_suffix": "dk",
    "c1.section.recommended_journey": "Önerilen Journey",
    "c1.activity_unknown_title": "Bilinmiyor (katalogda yok)",
    "c1.activity_meta": "Tür: {type} ({sub_type}) · Konu: {topic} · Süre: {minutes} dk",
    "c1.reason_label": "Gerekçe:",
    "c1.validation_help.title": "Bu doğrulama sonuçları ne anlama geliyor?",
    "c1.validation_help.body": (
        "**JSON geçerli**: Model cevabının uygulama tarafından JSON "
        "olarak okunabildiğini gösterir. İçeriğin doğru veya kaliteli "
        "olduğunu garanti etmez.\n\n"
        "**Pydantic doğrulaması**: Çıktının beklenen alanlara ve "
        "yapısal kurallara uyduğunu gösterir. Örneğin sıra numaraları, "
        "zorunlu alanlar ve pozitif süre değerleri kontrol edilir. "
        "Pedagojik uygunluğu garanti etmez.\n\n"
        "**İş kuralı doğrulaması**: Seçilen aktivite kimliklerinin "
        "katalogda bulunması, hariç tutulması gereken aktivitelerin "
        "seçilmemesi, sürelerin katalogla eşleşmesi, aktivite sayısının "
        "min/max sınırları içinde kalması, zorunlu konuların kapsanması "
        "ve (isteniyorsa) Journey'nin bir sınavla bitmesi gibi "
        "deterministik kontrolleri ifade eder.\n\n"
        "Hiçbir doğrulama katmanı tek başına önerinin en iyi "
        "pedagojik tavsiye olduğunu garanti etmez."
    ),
    "c1.user_prompt.brief_label": "JOURNEY TALEBİ (BRIEF):",
    "c1.user_prompt.catalog_label": "AKTİVİTE KATALOĞU:",
    "c1.user_prompt.instruction": "Yukarıdaki kurallara tam olarak uyan, yalnızca kataloğa dayalı bir Journey üret.",
}

EN = {
    "c1.page_subtitle": "C1 — Automatic Journey Generation",
    "c1.page_caption": (
        "An editable Journey is proposed using a Journey brief (audience, "
        "goal, required topics) and the existing activity catalog. The "
        "model may only select activities from the catalog, it does not "
        "generate new content."
    ),
    "c1.session_cost_caption": (
        "This amount only includes successful model calls made in the "
        "current session (including B1, B6 and C1). Resetting does not "
        "affect the CSV history."
    ),
    "c1.section.data_selection": "1. Sample/Upload Selection",
    "c1.data_source_label": "Data source",
    "c1.data_source.sample": "Use sample data",
    "c1.data_source.upload": "Upload my own files",
    "c1.brief_uploader_label": "Journey brief (JSON)",
    "c1.catalog_uploader_label": "Activity catalog (CSV)",
    "c1.info.upload_brief": "Please upload a Journey brief JSON file.",
    "c1.info.upload_catalog": "Please upload an activity catalog CSV file.",
    "c1.section.brief_preview": "2. Journey Brief Preview",
    "c1.info.provide_valid_brief": "Provide a valid Journey brief to preview.",
    "c1.section.catalog_preview": "3. Activity Catalog Preview",
    "c1.catalog_synthetic_note": (
        "Note: Rows whose title starts with '[Sample Data]' are synthetic/"
        "illustrative test data, not sourced from the real Mobixa system — "
        "in particular the real schema for 'LEARN' (learning card) "
        "activities has not been shared yet, so these rows are a guess. "
        "All other rows (numeric ids) are derived from real activity JSON "
        "files shared by the manager."
    ),
    "c1.info.provide_valid_catalog": "Provide a valid activity catalog to preview.",
    "c1.warning.unknown_excluded": (
        "Some excluded activity ids in the brief were not found in the catalog: {ids}"
    ),
    "c1.section.brief_summary": "4. Journey Brief Summary",
    "c1.metric.min_activities": "Min. activities",
    "c1.metric.max_activities": "Max. activities",
    "c1.metric.must_end_with_test": "Must end with a test",
    "c1.metric.required_topics_count": "Required topic count",
    "c1.section.generation": "5. Generation",
    "c1.generate_button": "Generate Journey with Both Models",
    "c1.error.missing_data": "Please provide a valid Journey brief and activity catalog first.",
    "c1.spinner.model_a": "Running Model A...",
    "c1.spinner.model_b": "Running Model B...",
    "c1.section.results": "6-7. Model Results",
    "c1.info.click_to_generate": "Click 'Generate Journey with Both Models' to see results.",
    "c1.configured_model_caption": "Configured model: {name}",
    "c1.business_check.passed": "Business rule validation: Passed",
    "c1.business_check.failed": "Business rule validation: Failed — {errors}",
    "c1.business_check.warnings": "Warnings: {warnings}",
    "c1.business_check.topics_coverage": "Required topic coverage: {covered}/{total}",
    "c1.audience_fit_label": "Audience fit:",
    "c1.strategy_summary_label": "Strategy summary:",
    "c1.total_minutes_label": "Total duration:",
    "c1.minutes_suffix": "min",
    "c1.section.recommended_journey": "Recommended Journey",
    "c1.activity_unknown_title": "Unknown (not in catalog)",
    "c1.activity_meta": "Type: {type} ({sub_type}) · Topic: {topic} · Duration: {minutes} min",
    "c1.reason_label": "Reason:",
    "c1.validation_help.title": "What do these validation results mean?",
    "c1.validation_help.body": (
        "**JSON valid**: Shows that the model's response could be parsed "
        "as JSON by the application. Does not guarantee the content is "
        "correct or high quality.\n\n"
        "**Pydantic validation**: Shows the output conforms to the "
        "expected fields and structural rules. For example, order "
        "numbers, required fields and positive durations are checked. "
        "Does not guarantee pedagogical suitability.\n\n"
        "**Business rule validation**: Refers to deterministic checks "
        "such as: selected activity ids exist in the catalog, excluded "
        "activities are not selected, durations match the catalog, the "
        "activity count stays within the min/max bounds, required topics "
        "are covered, and (if requested) the Journey ends with a test.\n\n"
        "No validation layer alone guarantees the recommendation is the "
        "best pedagogical choice."
    ),
    "c1.user_prompt.brief_label": "JOURNEY BRIEF:",
    "c1.user_prompt.catalog_label": "ACTIVITY CATALOG:",
    "c1.user_prompt.instruction": "Generate a Journey that fully complies with the rules above and is based only on the catalog.",
}
