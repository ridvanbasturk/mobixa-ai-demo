"""B6 (Rapor Değerlendirmesi) modülüne özgü metinler."""
from __future__ import annotations

TR = {
    "b6.page_subtitle": "B6 — Rapor Değerlendirmesi",
    "b6.page_caption": (
        "Rapor metrikleri Python ile deterministik olarak hesaplanır; yapay "
        "zekâ yalnızca bu metrikleri tespit ve öneri kartlarına dönüştürür."
    ),
    "b6.sidebar_comparison_note": (
        "Karşılaştırma amaçlıdır; bir sağlayıcının otomatik olarak daha iyi "
        "olduğu anlamına gelmez. Deterministik Python/Pandas metrikleri "
        "modelden bağımsızdır."
    ),
    "b6.session_cost_caption": (
        "Bu tutar yalnızca mevcut oturumda yapılan başarılı model çağrılarını "
        "içerir (B1 ve B6 dahil). Sıfırlamak CSV geçmişini etkilemez."
    ),
    "b6.section.report_period": "1. Rapor Dönemi",
    "b6.report_period_label": "Rapor dönemi (ör. 2026 Q2)",
    "b6.section.data_selection": "2. Örnek/Yükleme Seçimi",
    "b6.data_source_label": "Veri kaynağı",
    "b6.data_source.sample": "Örnek CSV kullan",
    "b6.data_source.upload": "CSV yükle",
    "b6.file_uploader_label": "CSV dosyası seçin",
    "b6.info.upload_csv": "Lütfen bir CSV dosyası yükleyin.",
    "b6.section.raw_preview": "3. Ham Veri Önizleme",
    "b6.info.select_valid_csv": "Önizlemek için geçerli bir CSV seçin veya yükleyin.",
    "b6.warning.missing_period": "Lütfen rapor dönemini girin.",
    "b6.section.metrics": "4. Hesaplanan Metrikler",
    "b6.metric.total_active_users": "Toplam Aktif Kullanıcı",
    "b6.metric.overall_completion_rate": "Genel Tamamlama Oranı (%)",
    "b6.metric.overall_average_quiz_score": "Genel Ortalama Quiz Puanı",
    "b6.metric.lowest_completion_group": "En düşük tamamlama oranı:",
    "b6.metric.highest_completion_group": "En yüksek tamamlama oranı:",
    "b6.metric.lowest_quiz_group": "En düşük quiz puanı:",
    "b6.metric.highest_quiz_group": "En yüksek quiz puanı:",
    "b6.section.risk_groups": "5. Risk Grupları",
    "b6.no_risk_groups": "Herhangi bir risk grubu tespit edilmedi.",
    "b6.section.metrics_json": "6. Tam Metrik JSON",
    "b6.section.generation": "7. Üretim",
    "b6.generate_button": "İki Modelle Değerlendirme Üret",
    "b6.error.missing_data": "Lütfen önce geçerli bir CSV ve rapor dönemi sağlayın.",
    "b6.spinner.model_a": "Model A çalıştırılıyor...",
    "b6.spinner.model_b": "Model B çalıştırılıyor...",
    "b6.section.results": "8-9. Model Sonuçları",
    "b6.info.click_to_generate": "Sonuçları görmek için önce 'İki Modelle Değerlendirme Üret' butonuna tıklayın.",
    "b6.configured_model_caption": "Yapılandırılmış model: {name}",
    "b6.numeric_check.passed": "Rakamsal kontrol: Geçti",
    "b6.numeric_check.warning": "Rakamsal kontrol: Uyarı — metriklerde bulunmayan sayılar: {numbers}",
    "b6.executive_summary_label": "Yönetici özeti:",
    "b6.section.insights": "Değerlendirmeler",
    "b6.severity_label": "Önem:",
    "b6.severity.low": "Düşük",
    "b6.severity.medium": "Orta",
    "b6.severity.high": "Yüksek",
    "b6.finding_label": "Tespit:",
    "b6.evidence_label": "Kanıt:",
    "b6.recommendation_label": "Öneri:",
    "b6.validation_help.title": "Bu doğrulama sonuçları ne anlama geliyor?",
    "b6.validation_help.body": (
        "**JSON geçerli**: Model cevabının uygulama tarafından JSON "
        "olarak okunabildiğini gösterir. İçeriğin doğru veya kaliteli "
        "olduğunu garanti etmez.\n\n"
        "**Pydantic doğrulaması**: Çıktının beklenen alanlara ve "
        "uygulamada tanımlı yapısal kurallara uyduğunu gösterir:\n"
        "- executive_summary alanının boş olmaması\n"
        "- Tam olarak dört değerlendirme döndürülmesi\n"
        "- title, finding, evidence ve recommendation alanlarının boş olmaması\n"
        "- severity değerinin low / medium / high değerlerinden biri olması\n"
        "- Tekrar eden değerlendirme başlıklarının reddedilmesi\n\n"
        "**Rakamsal kontrol**: Ayrı, basit bir kontroldür — her "
        "değerlendirmenin finding/evidence metninde geçen sayılar (başlıklar "
        "hariç) hesaplanan metrik JSON'undaki gerçek sayılarla "
        "karşılaştırılır; Türkçe ondalık virgülü desteklenir ve küçük "
        "bir tolerans uygulanır.\n\n"
        "Pydantic doğrulaması yapısal kurallara uyumu doğrular. "
        "Sayıların anlamsal olarak doğru olduğunu veya içeriğin "
        "metriklere tam olarak dayandığını garanti etmez — bunun için "
        "yukarıdaki rakamsal kontrol ve insan değerlendirmesi gerekir."
    ),
    "b6.human_eval.title": "İnsan Değerlendirmesi",
    "b6.human_eval.numeric_label": "Sayılar doğru mu?",
    "b6.human_eval.not_evaluated": "Değerlendirilmedi",
    "b6.human_eval.groundedness_label": "Çıktı metriklere dayanıyor mu?",
    "b6.human_eval.partial": "Kısmen",
    "b6.human_eval.actionability_label": "Uygulanabilirlik puanı",
    "b6.human_eval.language_quality_label": "Türkçe yönetim dili kalitesi",
    "b6.human_eval.causality_label": "Desteklenmeyen bir nedensellik var mı?",
    "b6.human_eval.notes_label": "Notlar",
    "b6.human_eval.save_button": "Değerlendirmeyi Kaydet",
    "b6.human_eval.saved": "Değerlendirme kaydedildi.",
    "b6.human_eval.save_failed": "Değerlendirme kaydedilemedi: eşleşen CSV kaydı bulunamadı.",
    "b6.user_prompt.metrics_label": "METRİK JSON'U:",
    "b6.user_prompt.instruction": "Bu metriklerden, yukarıdaki kurallara tam olarak uyan 4 değerlendirme üret.",
}

EN = {
    "b6.page_subtitle": "B6 — Report Insights",
    "b6.page_caption": (
        "Report metrics are computed deterministically with Python; AI "
        "only turns these metrics into findings and recommendation cards."
    ),
    "b6.sidebar_comparison_note": (
        "For comparison purposes only; does not imply either provider is "
        "automatically better. Deterministic Python/Pandas metrics are "
        "independent of the model."
    ),
    "b6.session_cost_caption": (
        "This amount only includes successful model calls made in the "
        "current session (including B1 and B6). Resetting does not "
        "affect the CSV history."
    ),
    "b6.section.report_period": "1. Report Period",
    "b6.report_period_label": "Report period (e.g. 2026 Q2)",
    "b6.section.data_selection": "2. Sample/Upload Selection",
    "b6.data_source_label": "Data source",
    "b6.data_source.sample": "Use sample CSV",
    "b6.data_source.upload": "Upload CSV",
    "b6.file_uploader_label": "Choose a CSV file",
    "b6.info.upload_csv": "Please upload a CSV file.",
    "b6.section.raw_preview": "3. Raw Data Preview",
    "b6.info.select_valid_csv": "Select or upload a valid CSV to preview.",
    "b6.warning.missing_period": "Please enter the report period.",
    "b6.section.metrics": "4. Computed Metrics",
    "b6.metric.total_active_users": "Total Active Users",
    "b6.metric.overall_completion_rate": "Overall Completion Rate (%)",
    "b6.metric.overall_average_quiz_score": "Overall Average Quiz Score",
    "b6.metric.lowest_completion_group": "Lowest completion rate:",
    "b6.metric.highest_completion_group": "Highest completion rate:",
    "b6.metric.lowest_quiz_group": "Lowest quiz score:",
    "b6.metric.highest_quiz_group": "Highest quiz score:",
    "b6.section.risk_groups": "5. Risk Groups",
    "b6.no_risk_groups": "No risk groups detected.",
    "b6.section.metrics_json": "6. Full Metrics JSON",
    "b6.section.generation": "7. Generation",
    "b6.generate_button": "Generate Insights with Both Models",
    "b6.error.missing_data": "Please provide a valid CSV and report period first.",
    "b6.spinner.model_a": "Running Model A...",
    "b6.spinner.model_b": "Running Model B...",
    "b6.section.results": "8-9. Model Results",
    "b6.info.click_to_generate": "Click 'Generate Insights with Both Models' to see results.",
    "b6.configured_model_caption": "Configured model: {name}",
    "b6.numeric_check.passed": "Numeric check: Passed",
    "b6.numeric_check.warning": "Numeric check: Warning — numbers not found in metrics: {numbers}",
    "b6.executive_summary_label": "Executive summary:",
    "b6.section.insights": "Insights",
    "b6.severity_label": "Severity:",
    "b6.severity.low": "Low",
    "b6.severity.medium": "Medium",
    "b6.severity.high": "High",
    "b6.finding_label": "Finding:",
    "b6.evidence_label": "Evidence:",
    "b6.recommendation_label": "Recommendation:",
    "b6.validation_help.title": "What do these validation results mean?",
    "b6.validation_help.body": (
        "**JSON valid**: Shows that the model's response could be parsed "
        "as JSON by the application. Does not guarantee the content is "
        "correct or high quality.\n\n"
        "**Pydantic validation**: Shows the output conforms to the "
        "expected fields and structural rules defined in the app:\n"
        "- executive_summary is not blank\n"
        "- Exactly four insights are returned\n"
        "- title, finding, evidence and recommendation fields are not blank\n"
        "- severity is one of low / medium / high\n"
        "- Duplicate insight titles are rejected\n\n"
        "**Numeric check**: A separate, simple check — the numbers "
        "appearing in each insight's finding/evidence text (excluding "
        "titles) are compared against the actual numbers in the computed "
        "metrics JSON; a small tolerance is applied.\n\n"
        "Pydantic validation confirms structural compliance. It does not "
        "guarantee the numbers are semantically correct or that the "
        "content is fully grounded in the metrics — for that, use the "
        "numeric check above and human evaluation."
    ),
    "b6.human_eval.title": "Human Evaluation",
    "b6.human_eval.numeric_label": "Are the numbers correct?",
    "b6.human_eval.not_evaluated": "Not evaluated",
    "b6.human_eval.groundedness_label": "Is the output grounded in the metrics?",
    "b6.human_eval.partial": "Partially",
    "b6.human_eval.actionability_label": "Actionability score",
    "b6.human_eval.language_quality_label": "Management language quality",
    "b6.human_eval.causality_label": "Is there any unsupported causal claim?",
    "b6.human_eval.notes_label": "Notes",
    "b6.human_eval.save_button": "Save Evaluation",
    "b6.human_eval.saved": "Evaluation saved.",
    "b6.human_eval.save_failed": "Could not save evaluation: no matching CSV record found.",
    "b6.user_prompt.metrics_label": "METRICS JSON:",
    "b6.user_prompt.instruction": "Generate 4 insights from these metrics that fully comply with the rules above.",
}
