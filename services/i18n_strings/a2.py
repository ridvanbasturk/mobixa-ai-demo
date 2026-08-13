"""A2 (Destek/Onboarding Chatbot) modülüne özgü metinler."""
from __future__ import annotations

TR = {
    "a2.page_subtitle": "A2 — Destek/Oryantasyon Sohbet Botu",
    "a2.page_caption": (
        "Wiki (onaylı bilgi kaynağı), Yetenekler (aktif yetenekler) ve "
        "Eklentiler (gelecek entegrasyonlar) açıkça ayrılmıştır. Cevaplar "
        "yalnızca onaylı wiki bağlamına dayanır."
    ),
    "a2.tab.chatbot": "Sohbet Botu",
    "a2.tab.wiki": "Bilgi Tabanı",
    "a2.tab.skills": "Yetenekler ve Entegrasyonlar",
    "a2.second_gemma_missing": "İkinci doğrulanmış Gemma modeli bulunmadığı için tek aktif Gemma modeli kullanılıyor.",
    "a2.sidebar_pair_note": (
        "A2, B1/B6/C1'den farklı bir model çifti kullanır — aktif yanıt "
        "üretim modelleri YALNIZCA Gemma'dır (Kimi/DeepSeek artık aktif değil)."
    ),
    "a2.session_cost_caption": (
        "Bu tutar yalnızca mevcut oturumda yapılan başarılı model çağrılarını "
        "içerir (B1, B6, C1 ve A2 dahil). Sıfırlamak CSV geçmişini etkilemez."
    ),
    "a2.retrieved_sources_title": "Getirilen Kaynaklar",
    "a2.no_relevant_source_warning": (
        "Onaylı wiki içinde yeterince alakalı bir kayıt bulunamadı. "
        "Modele hiçbir kaynak bağlamı verilmedi; bu soru deterministik "
        "olarak yetersiz desteklenmiş kabul edilir."
    ),
    "a2.below_threshold_caption": "(Bilgi amaçlı: bu kayıtlar eşik değerin altında kaldı.)",
    "a2.validation_help.title": "Bu doğrulama sonuçları ne anlama geliyor?",
    "a2.validation_help.body": (
        "**JSON geçerli**: Cevabın JSON olarak okunabildiğini gösterir.\n\n"
        "**Pydantic doğrulaması**: Beklenen alanların ve veri türlerinin "
        "mevcut olduğunu gösterir.\n\n"
        "**Kaynak doğrulaması**: Kullanılan kaynak kimliklerinin gerçekten "
        "getirilen ve onaylanmış wiki kayıtları içinde bulunduğunu "
        "gösterir.\n\n"
        "**Dayanak kontrolü**: Bazı açık kaynak dışı iddiaları, sahte "
        "fiyatları, bilinmeyen destek kanallarını ve 'bilgi yok' "
        "ifadesini 'özellik yok' şeklinde değiştiren kesin iddiaları "
        "yakalamaya çalışır.\n\n"
        "Bu kontroller teknik tutarlılığı artırır; cevabın tüm anlamını "
        "ve doğruluğunu kesin olarak garanti etmez."
    ),
    "a2.source_validation.passed": "Kaynak doğrulaması: Geçti",
    "a2.source_validation.failed": "Kaynak doğrulaması: Başarısız — bilinmeyen kaynak(lar): {ids}",
    "a2.grounding.passed": "Dayanak kontrolü: Geçti",
    "a2.grounding.failed": "Dayanak kontrolü: Başarısız — {errors}",
    "a2.grounding.warnings": "Uyarılar: {warnings}",
    "a2.grounding.not_run": "Kaynak/dayanak kontrolü: şema doğrulaması başarısız olduğu için çalıştırılamadı.",
    "a2.answer_label": "Cevap:",
    "a2.cited_sources_label": "Atıf yapılan kaynaklar:",
    "a2.support_reason_label": "Gerekçe (support_reason):",
    "a2.model_escalation_label": "Model'in yönlendirme önerisi:",
    "a2.no_value": "Yok",
    "a2.final_escalation_yes": "Nihai (deterministik) yönlendirme kararı: Evet",
    "a2.final_escalation_no": "Nihai (deterministik) yönlendirme kararı: Hayır",
    "a2.usage.not_measured": "Ölçülemedi",
    "a2.usage.none": "Kaynak kullanılmadı",
    "a2.usage.valid_of_total": "{valid}/{total} geçerli",
    "a2.comparison_extra_caption": (
        "Yalnızca bu çalıştırmadan elde edilen ölçülebilir teknik verilere "
        "dayanır. Anlamsal bir kalite yargısı değildir. İki Gemma varyantı "
        "karşılaştırılır; bir sağlayıcı karşılaştırması değildir."
    ),
    "a2.comparison_no_second_gemma": (
        "İkinci doğrulanmış Gemma modeli bulunmadığı için tek aktif "
        "Gemma modeli kullanılıyor — karşılaştırma özeti gösterilmez."
    ),
    "a2.source_id_usage_line": "Geçerli kaynak ID kullanımı — {label_a}: {usage_a}; {label_b}: {usage_b}",
    "a2.sample_questions_title": "Örnek Sorular",
    "a2.spinner.plan_a": "{plan} çalıştırılıyor...",
    "a2.wiki.title": "Bilgi Tabanı (Wiki)",
    "a2.wiki.info": (
        "Bu demo yerel örnek wiki kullanır. Üretim ortamında bu katman "
        "Confluence, Notion, yardım merkezi veya Bedrock Knowledge Bases "
        "ile değiştirilebilir."
    ),
    "a2.wiki.search_label": "Ara (başlık veya içerik)",
    "a2.wiki.roles_label": "Roller:",
    "a2.wiki.product_area_label": "Ürün alanı:",
    "a2.wiki.version_label": "Sürüm:",
    "a2.wiki.last_updated_label": "Son güncelleme:",
    "a2.skills.active_title": "Aktif PoC Yetenekleri",
    "a2.skills.future_title": "Gelecek Eklenti Planları",
    "a2.skills.future_caption": (
        "Aşağıdaki eklentiler henüz gerçek bir Mobixa backend "
        "entegrasyonuna sahip değildir; hiçbiri şu anda çalıştırılmaz."
    ),
    "a2.skills.purpose_label": "Amaç:",
    "a2.skills.expected_input_label": "Beklenen girdi:",
    "a2.skills.expected_output_label": "Beklenen çıktı:",
    "a2.skills.simulation_title": "Simülasyon: Aktivite Durumu Sorgulama",
    "a2.skills.simulation_caption": (
        "Aşağıdaki demo gerçek bir backend'e bağlı değildir; yalnızca sabit "
        "örnek veri döndürür."
    ),
    "a2.skills.activity_id_label": "Aktivite ID",
    "a2.skills.simulation_button": "Durumu Sorgula (Simülasyon)",
    "a2.user_prompt.question_label": "KULLANICI SORUSU:",
    "a2.user_prompt.context_label": "GETİRİLEN ONAYLI WIKI BAĞLAMI:",
    "a2.user_prompt.no_context": "(Getirilen bağlam yok — onaylı wiki içinde ilgili bir kayıt bulunamadı.)",
    "a2.assistant_name": "Mobixa Asistanı",
    "a2.chat_greeting": (
        "Merhaba! Mobixa hakkında sorularınızı yanıtlamaya hazırım. "
        "Aşağıdaki örnek sorulardan birini seçebilir ya da kendi "
        "sorunuzu yazabilirsiniz."
    ),
    "a2.chat_input_placeholder": "Bir soru yazın...",
    "a2.suggestions_title": "Örnek sorular",
    "a2.comparison_mode_label": "Karşılaştırma Modu",
    "a2.comparison_mode_help": (
        "Açıldığında her soru ikinci bir Gemma varyantıyla da çalıştırılır "
        "ve iki modelin cevabı teknik detaylarda karşılaştırılır. Kapalıyken "
        "yalnızca birincil model çalışır — daha hızlı ve daha az maliyetli."
    ),
    "a2.citations_label": "📚 Kaynak:",
    "a2.escalation_note_chat": "🧑‍💼 Bu konuda daha fazla yardım için destek ekibine yönlendirilmeniz öneriliyor.",
    "a2.answer_fallback_failed": (
        "Şu anda bu soruyu yanıtlayamıyorum, teknik bir sorun oluştu. "
        "Detaylar için aşağıdaki 'Teknik detaylar' bölümüne bakabilir veya "
        "destek ekibiyle iletişime geçebilirsiniz."
    ),
    "a2.answer_fallback_schema_invalid": (
        "Bu soru için bir yanıt üretildi ama beklenen formata uymadığı için "
        "gösterilemiyor. Detaylar için aşağıdaki 'Teknik detaylar' "
        "bölümüne bakabilirsiniz."
    ),
    "a2.tech_details_expander": "Teknik detaylar",
    "a2.tech_details_primary_label": "Birincil model",
    "a2.tech_details_comparison_label": "Karşılaştırma (ikinci model)",
    "a2.comparison_off_note": (
        "Bu soru sorulduğunda Karşılaştırma Modu kapalıydı, ikinci model "
        "çağrılmadı."
    ),
}

EN = {
    "a2.page_subtitle": "A2 — Support/Onboarding Chatbot",
    "a2.page_caption": (
        "Wiki (approved knowledge source), Skills (currently active "
        "capabilities) and Plugins (future integrations) are clearly "
        "separated. Answers are based only on the approved wiki context."
    ),
    "a2.tab.chatbot": "Chatbot",
    "a2.tab.wiki": "Knowledge Base",
    "a2.tab.skills": "Skills & Integrations",
    "a2.second_gemma_missing": "No second verified Gemma model is configured, so only the single active Gemma model is used.",
    "a2.sidebar_pair_note": (
        "A2 uses a different model pair than B1/B6/C1 — the active "
        "response generation models are Gemma ONLY (Kimi/DeepSeek are no "
        "longer active)."
    ),
    "a2.session_cost_caption": (
        "This amount only includes successful model calls made in the "
        "current session (including B1, B6, C1 and A2). Resetting does "
        "not affect the CSV history."
    ),
    "a2.retrieved_sources_title": "Retrieved Sources",
    "a2.no_relevant_source_warning": (
        "No sufficiently relevant record was found in the approved wiki. "
        "No source context was given to the model; this question is "
        "deterministically considered insufficiently supported."
    ),
    "a2.below_threshold_caption": "(Informational: these records were below the relevance threshold.)",
    "a2.validation_help.title": "What do these validation results mean?",
    "a2.validation_help.body": (
        "**JSON valid**: Shows the response could be parsed as JSON.\n\n"
        "**Pydantic validation**: Shows the expected fields and data "
        "types are present.\n\n"
        "**Source validation**: Shows that the cited source ids actually "
        "exist among the retrieved, approved wiki records.\n\n"
        "**Grounding check**: Attempts to catch some out-of-source "
        "claims, fabricated prices, unknown support channels, and "
        "absolute claims that turn 'no information' into 'no such "
        "feature'.\n\n"
        "These checks improve technical consistency; they do not "
        "definitively guarantee the full meaning and correctness of the "
        "answer."
    ),
    "a2.source_validation.passed": "Source validation: Passed",
    "a2.source_validation.failed": "Source validation: Failed — unknown source(s): {ids}",
    "a2.grounding.passed": "Grounding check: Passed",
    "a2.grounding.failed": "Grounding check: Failed — {errors}",
    "a2.grounding.warnings": "Warnings: {warnings}",
    "a2.grounding.not_run": "Source/grounding check: could not run because schema validation failed.",
    "a2.answer_label": "Answer:",
    "a2.cited_sources_label": "Cited sources:",
    "a2.support_reason_label": "Reason (support_reason):",
    "a2.model_escalation_label": "Model's escalation suggestion:",
    "a2.no_value": "N/A",
    "a2.final_escalation_yes": "Final (deterministic) escalation decision: Yes",
    "a2.final_escalation_no": "Final (deterministic) escalation decision: No",
    "a2.usage.not_measured": "Not measured",
    "a2.usage.none": "No sources used",
    "a2.usage.valid_of_total": "{valid}/{total} valid",
    "a2.comparison_extra_caption": (
        "Based only on measurable technical data from this run. Not a "
        "semantic quality judgment. Compares two Gemma variants; not a "
        "provider comparison."
    ),
    "a2.comparison_no_second_gemma": (
        "No second verified Gemma model is configured, so only the "
        "single active Gemma model is used — no comparison summary is "
        "shown."
    ),
    "a2.source_id_usage_line": "Valid source id usage — {label_a}: {usage_a}; {label_b}: {usage_b}",
    "a2.sample_questions_title": "Sample Questions",
    "a2.spinner.plan_a": "Running {plan}...",
    "a2.wiki.title": "Knowledge Base (Wiki)",
    "a2.wiki.info": (
        "This demo uses a local sample wiki. In production this layer "
        "can be replaced with Confluence, Notion, a help center, or "
        "Bedrock Knowledge Bases."
    ),
    "a2.wiki.search_label": "Search (title or content)",
    "a2.wiki.roles_label": "Roles:",
    "a2.wiki.product_area_label": "Product area:",
    "a2.wiki.version_label": "Version:",
    "a2.wiki.last_updated_label": "Last updated:",
    "a2.skills.active_title": "Active PoC Skills",
    "a2.skills.future_title": "Future Plugin Plans",
    "a2.skills.future_caption": (
        "The plugins below do not yet have a real Mobixa backend "
        "integration; none of them run at this time."
    ),
    "a2.skills.purpose_label": "Purpose:",
    "a2.skills.expected_input_label": "Expected input:",
    "a2.skills.expected_output_label": "Expected output:",
    "a2.skills.simulation_title": "Simulation: Activity Status Lookup",
    "a2.skills.simulation_caption": (
        "The demo below is not connected to a real backend; it only "
        "returns fixed sample data."
    ),
    "a2.skills.activity_id_label": "Activity ID",
    "a2.skills.simulation_button": "Look Up Status (Simulation)",
    "a2.user_prompt.question_label": "USER QUESTION:",
    "a2.user_prompt.context_label": "RETRIEVED APPROVED WIKI CONTEXT:",
    "a2.user_prompt.no_context": "(No context retrieved — no relevant record found in the approved wiki.)",
    "a2.assistant_name": "Mobixa Assistant",
    "a2.chat_greeting": (
        "Hi! I'm ready to answer your questions about Mobixa. Pick one of "
        "the sample questions below or type your own."
    ),
    "a2.chat_input_placeholder": "Type a question...",
    "a2.suggestions_title": "Sample questions",
    "a2.comparison_mode_label": "Comparison Mode",
    "a2.comparison_mode_help": (
        "When on, every question is also run through a second Gemma "
        "variant and the two answers are compared in the technical "
        "details. When off, only the primary model runs — faster and "
        "cheaper."
    ),
    "a2.citations_label": "📚 Source:",
    "a2.escalation_note_chat": "🧑‍💼 For further help with this, I'd recommend reaching out to the support team.",
    "a2.answer_fallback_failed": (
        "I can't answer this question right now, a technical issue "
        "occurred. See the 'Technical details' section below for more, "
        "or contact the support team."
    ),
    "a2.answer_fallback_schema_invalid": (
        "An answer was generated for this question but it doesn't match "
        "the expected format, so it can't be shown. See the 'Technical "
        "details' section below."
    ),
    "a2.tech_details_expander": "Technical details",
    "a2.tech_details_primary_label": "Primary model",
    "a2.tech_details_comparison_label": "Comparison (second model)",
    "a2.comparison_off_note": (
        "Comparison Mode was off when this question was asked, the "
        "second model was not called."
    ),
}
