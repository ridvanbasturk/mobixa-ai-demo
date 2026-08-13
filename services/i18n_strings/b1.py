"""B1 (İçerikten Otomatik Soru ve Aktivite Üretimi) modülüne özgü metinler."""
from __future__ import annotations

TR = {
    "b1.page_subtitle": "B1 — İçerikten Otomatik Soru ve Aktivite Üretimi",
    "b1.difficulty.easy": "Kolay",
    "b1.difficulty.medium": "Orta",
    "b1.difficulty.hard": "Zor",
    "b1.difficulty.mixed": "Karışık",
    "b1.conn_test.caption": (
        "Bağlantıyı Test Et: yalnızca seçilen tek bir modeli, kısa bir "
        "prompt ile çağırır. Değerlendirme CSV'sine yazılmaz ve oturum "
        "maliyetine eklenmez."
    ),
    "b1.conn_test.radio_label": "Test edilecek model",
    "b1.conn_test.option_a": "Model A",
    "b1.conn_test.option_b": "Model B",
    "b1.conn_test.button": "Bağlantıyı Test Et",
    "b1.conn_test.spinner": "{choice} test ediliyor...",
    "b1.conn_test.endpoint_label": "Uç nokta:",
    "b1.conn_test.region_label": "Bölge:",
    "b1.conn_test.model_label": "Model:",
    "b1.conn_test.timeout_label": "Zaman aşımı ayarları:",
    "b1.conn_test.timeout_value": (
        "bağlantı {connect:.0f} sn, istek {request:.0f} sn, "
        "maksimum yeniden deneme {retries}"
    ),
    "b1.conn_test.latency_label": "Gecikme:",
    "b1.conn_test.latency_value": "{latency:.2f} sn",
    "b1.conn_test.success": "Durum: Başarılı — yanıt: {snippet}",
    "b1.conn_test.failure": "Durum: Başarısız ({category}) — {error}",
    "b1.section.content_input": "1. İçerik Girişi",
    "b1.content_source_label": "İçerik kaynağı",
    "b1.content_source.paste": "Metin yapıştır",
    "b1.content_source.upload": "Dosya yükle (TXT/PDF/DOCX/PPTX)",
    "b1.content_source.sample": "Hazır örnek metni kullan",
    "b1.content_paste_label": "Eğitim içeriğini yapıştırın",
    "b1.file_uploader_label": "Dosya seçin",
    "b1.file_extract_success": "Metin başarıyla çıkarıldı ({count} karakter)",
    "b1.file_extract_preview": "Çıkarılan metni önizle",
    "b1.sample_text_info": "Hazır örnek metin kullanılıyor: information_security.txt",
    "b1.sample_text_preview": "Örnek metni önizle",
    "b1.section.generation_settings": "2. Üretim Ayarları",
    "b1.question_count_label": "Soru sayısı",
    "b1.difficulty_label": "Zorluk",
    "b1.generate_cards_label": "Öğrenme kartı oluştur",
    "b1.section.generation": "3. Üretim",
    "b1.generate_button": "İki Modelle Üret",
    "b1.error.no_content": "Lütfen önce bir eğitim içeriği girin.",
    "b1.warning.generation_in_progress": "Bir üretim zaten devam ediyor, lütfen bekleyin.",
    "b1.spinner.model_a": "Model A çalıştırılıyor...",
    "b1.spinner.model_b": "Model B çalıştırılıyor...",
    "b1.section.results": "4. Model Sonuçları",
    "b1.warning.comparison_needs_both": (
        "Karşılaştırma özeti yalnızca her iki model için de bir sonuç "
        "mevcut olduğunda gösterilir."
    ),
    "b1.info.no_result_for_plan": "{plan} için sonuç alınamadı (beklenmeyen bir hata oluştu).",
    "b1.info.click_to_generate": "Sonuçları görmek için önce 'İki Modelle Üret' butonuna tıklayın.",
    "b1.configured_model_caption": "Yapılandırılmış model: {name}",
    "b1.title_label": "Başlık:",
    "b1.section.questions": "Sorular",
    "b1.explanation_label": "Açıklama:",
    "b1.source_quote_label": "Kaynak alıntı:",
    "b1.category_meta": "Zorluk: {difficulty} · Kategori: {category}",
    "b1.section.learning_cards": "Öğrenme Kartları",
    "b1.key_takeaway_label": "Anahtar çıkarım:",
    "b1.validation_help.title": "Bu doğrulama sonuçları ne anlama geliyor?",
    "b1.validation_help.body": (
        "**JSON geçerli**: Model cevabının uygulama tarafından JSON "
        "olarak okunabildiğini gösterir. İçeriğin doğru veya kaliteli "
        "olduğunu garanti etmez.\n\n"
        "**Pydantic doğrulaması**: Çıktının beklenen alanlara ve "
        "uygulamada tanımlı yapısal kurallara uyduğunu gösterir:\n"
        "- Her soruda tam dört seçenek olması\n"
        "- correct_answer değerinin 1 ile 4 arasında olması\n"
        "- Zorunlu alanların (soru, seçenekler, açıklama, kaynak "
        "alıntı, başlık, öğrenme kartı alanları) boş olmaması\n"
        "- İstenen soru sayısının üretilmiş olması\n"
        "- Tekrar eden soruların reddedilmesi\n"
        "- Öğrenme kartı gereksinimlerinin karşılanması (istendiyse "
        "en az bir kart)\n\n"
        "Pydantic doğrulaması yapısal kurallara uyumu doğrular. Cevap "
        "anahtarının anlamsal olarak doğru olduğunu veya üretilen "
        "içeriğin kaynağa tam olarak dayandığını garanti etmez."
    ),
    "b1.human_eval.title": "İnsan Değerlendirmesi",
    "b1.human_eval.answer_key_label": "Cevap anahtarları doğru mu?",
    "b1.human_eval.not_evaluated": "Değerlendirilmedi",
    "b1.human_eval.groundedness_label": "Çıktı kaynak içeriğe dayanıyor mu?",
    "b1.human_eval.partial": "Kısmen",
    "b1.human_eval.language_quality_label": "Türkçe dil ve soru kalitesi",
    "b1.human_eval.notes_label": "Değerlendirici notları",
    "b1.human_eval.save_button": "Değerlendirmeyi Kaydet",
    "b1.human_eval.saved": "Değerlendirme kaydedildi.",
    "b1.human_eval.save_failed": "Değerlendirme kaydedilemedi: eşleşen CSV kaydı bulunamadı.",
    "b1.user_prompt.content_label": "EĞİTİM İÇERİĞİ:",
    "b1.user_prompt.instruction": "Bu içerikten tam olarak {count} adet çoktan seçmeli soru üret.",
    "b1.user_prompt.difficulty_mixed": "Zorluk seviyesi karışık (easy, medium, hard) olsun.",
    "b1.user_prompt.difficulty_fixed": "Tüm soruların zorluk seviyesi '{difficulty}' olsun.",
    "b1.user_prompt.cards_yes": "Ayrıca en az 3 adet öğrenme kartı üret.",
    "b1.user_prompt.cards_no": "learning_cards alanını boş liste olarak bırak.",
}

EN = {
    "b1.page_subtitle": "B1 — Automatic Question & Activity Generation from Content",
    "b1.difficulty.easy": "Easy",
    "b1.difficulty.medium": "Medium",
    "b1.difficulty.hard": "Hard",
    "b1.difficulty.mixed": "Mixed",
    "b1.conn_test.caption": (
        "Test Connection: calls only the single selected model with a "
        "short prompt. Not written to the evaluation CSV and not added "
        "to the session cost."
    ),
    "b1.conn_test.radio_label": "Model to test",
    "b1.conn_test.option_a": "Model A",
    "b1.conn_test.option_b": "Model B",
    "b1.conn_test.button": "Test Connection",
    "b1.conn_test.spinner": "Testing {choice}...",
    "b1.conn_test.endpoint_label": "Endpoint:",
    "b1.conn_test.region_label": "Region:",
    "b1.conn_test.model_label": "Model:",
    "b1.conn_test.timeout_label": "Timeout settings:",
    "b1.conn_test.timeout_value": (
        "connect {connect:.0f}s, request {request:.0f}s, "
        "max retries {retries}"
    ),
    "b1.conn_test.latency_label": "Latency:",
    "b1.conn_test.latency_value": "{latency:.2f}s",
    "b1.conn_test.success": "Status: Successful — response: {snippet}",
    "b1.conn_test.failure": "Status: Failed ({category}) — {error}",
    "b1.section.content_input": "1. Content Input",
    "b1.content_source_label": "Content source",
    "b1.content_source.paste": "Paste text",
    "b1.content_source.upload": "Upload file (TXT/PDF/DOCX/PPTX)",
    "b1.content_source.sample": "Use sample text",
    "b1.content_paste_label": "Paste the training content",
    "b1.file_uploader_label": "Choose a file",
    "b1.file_extract_success": "Text extracted successfully ({count} characters)",
    "b1.file_extract_preview": "Preview extracted text",
    "b1.sample_text_info": "Using the sample text: information_security.txt",
    "b1.sample_text_preview": "Preview sample text",
    "b1.section.generation_settings": "2. Generation Settings",
    "b1.question_count_label": "Number of questions",
    "b1.difficulty_label": "Difficulty",
    "b1.generate_cards_label": "Generate learning card",
    "b1.section.generation": "3. Generation",
    "b1.generate_button": "Generate with Both Models",
    "b1.error.no_content": "Please enter training content first.",
    "b1.warning.generation_in_progress": "A generation is already in progress, please wait.",
    "b1.spinner.model_a": "Running Model A...",
    "b1.spinner.model_b": "Running Model B...",
    "b1.section.results": "4. Model Results",
    "b1.warning.comparison_needs_both": (
        "The comparison summary is only shown when a result is available "
        "for both models."
    ),
    "b1.info.no_result_for_plan": "No result for {plan} (an unexpected error occurred).",
    "b1.info.click_to_generate": "Click 'Generate with Both Models' to see results.",
    "b1.configured_model_caption": "Configured model: {name}",
    "b1.title_label": "Title:",
    "b1.section.questions": "Questions",
    "b1.explanation_label": "Explanation:",
    "b1.source_quote_label": "Source quote:",
    "b1.category_meta": "Difficulty: {difficulty} · Category: {category}",
    "b1.section.learning_cards": "Learning Cards",
    "b1.key_takeaway_label": "Key takeaway:",
    "b1.validation_help.title": "What do these validation results mean?",
    "b1.validation_help.body": (
        "**JSON valid**: Shows that the model's response could be parsed "
        "as JSON by the application. Does not guarantee the content is "
        "correct or high quality.\n\n"
        "**Pydantic validation**: Shows the output conforms to the "
        "expected fields and structural rules defined in the app:\n"
        "- Exactly four options per question\n"
        "- correct_answer is between 1 and 4\n"
        "- Required fields (question, options, explanation, source "
        "quote, title, learning card fields) are not blank\n"
        "- The requested number of questions was generated\n"
        "- Duplicate questions are rejected\n"
        "- Learning card requirements are met (at least one card if "
        "requested)\n\n"
        "Pydantic validation confirms structural compliance. It does not "
        "guarantee the answer key is semantically correct or that the "
        "generated content is fully grounded in the source."
    ),
    "b1.human_eval.title": "Human Evaluation",
    "b1.human_eval.answer_key_label": "Are the answer keys correct?",
    "b1.human_eval.not_evaluated": "Not evaluated",
    "b1.human_eval.groundedness_label": "Is the output grounded in the source content?",
    "b1.human_eval.partial": "Partially",
    "b1.human_eval.language_quality_label": "Language and question quality",
    "b1.human_eval.notes_label": "Reviewer notes",
    "b1.human_eval.save_button": "Save Evaluation",
    "b1.human_eval.saved": "Evaluation saved.",
    "b1.human_eval.save_failed": "Could not save evaluation: no matching CSV record found.",
    "b1.user_prompt.content_label": "TRAINING CONTENT:",
    "b1.user_prompt.instruction": "Generate exactly {count} multiple-choice questions from this content.",
    "b1.user_prompt.difficulty_mixed": "Use a mixed difficulty level (easy, medium, hard).",
    "b1.user_prompt.difficulty_fixed": "All questions should have difficulty level '{difficulty}'.",
    "b1.user_prompt.cards_yes": "Also generate at least 3 learning cards.",
    "b1.user_prompt.cards_no": "Leave the learning_cards field as an empty list.",
}
