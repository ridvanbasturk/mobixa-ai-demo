"""A1 (Ürün Turu Stüdyosu) modülüne özgü metinler.

A1, diğer modüllerden farklı çalışır: bir içerik/analiz modülü değil, görsel
bir ajanın çalışan uygulamayı gerçekten gezip video kaydettiği bir stüdyodur.
Bu yüzden "iki modeli karşılaştırma" düzeni yoktur; tek bir sürücü ajan
vardır.
"""
from __future__ import annotations

TR = {
    "a1.page_subtitle": "A1 — Otomatik Ürün Turu Stüdyosu",
    "a1.page_caption": (
        "Görsel bir YZ ajanı çalışan uygulamayı kendi gezer: her adımda "
        "ekrana bakar, nereye tıklayacağına karar verir, imleci oraya "
        "götürür ve tüm oturumu video olarak kaydeder. Anlatım altyazıya "
        "gömülür ve yapılandırılmışsa Amazon Polly ile seslendirilir."
    ),
    "a1.how_it_works_title": "Bu nasıl çalışıyor?",
    "a1.how_it_works_body": (
        "**1. Uygulama başlatılır** — kaydedilecek uygulama ayrı bir portta "
        "kendi süreci olarak çalıştırılır, böylece bu sayfa etkilenmez.\n\n"
        "**2. Ajan ekrana bakar** — her adımda gerçek bir ekran görüntüsü "
        "alınır ve sayfadaki gerçek arayüz öğeleri (buton, kutu, sekme) "
        "tarayıcının kendisinden okunur.\n\n"
        "**3. Ajan karar verir** — görsel model o anki ekranı görüp tek bir "
        "sonraki adıma karar verir. Önceden yazılmış bir senaryo yoktur; "
        "ajan bir önceki adımın sonucunu görerek ilerler.\n\n"
        "**4. Karar denetlenir** — seçilen öğe ekranda gerçekten var mı diye "
        "deterministik olarak kontrol edilir. Bu, imlecin boşluğa tıklamasını "
        "engeller; ajanın karar özgürlüğünü kısıtlamaz.\n\n"
        "**5. İmleç hareket eder ve kaydedilir** — imleç hedefe yumuşak bir "
        "animasyonla gider, tıklar, Streamlit'in işi bitene kadar beklenir."
    ),
    "a1.section.settings": "1. Kayıt Ayarları",
    "a1.module_label": "Turu çekilecek modül",
    "a1.language_label": "Tur dili",
    "a1.max_steps_label": "Maksimum adım sayısı",
    "a1.max_steps_help": (
        "Her adım bir görsel model çağrısıdır. Ajan turu daha erken "
        "tamamlarsa bu sınıra ulaşılmaz."
    ),
    "a1.enable_voice_label": "Amazon Polly ile seslendir",
    "a1.enable_voice_help": (
        "Kapatılırsa video sessiz ama altyazılı üretilir. Polly "
        "yapılandırılmamışsa zaten otomatik olarak sessize düşer."
    ),
    "a1.voice_ready": "Seslendirme hazır: {detail}",
    "a1.voice_unavailable": "Seslendirme kullanılamıyor: {detail} — video sessiz ama altyazılı üretilecek.",
    "a1.cost_warning": (
        "**Maliyet uyarısı:** Ajan turu çekerken gerçek arayüzü kullanır; "
        "bir üretim butonuna basarsa o modülün gerçek model çağrıları da "
        "tetiklenir. Kayıt başına yaklaşık {steps} görsel model çağrısı + "
        "tetiklenen üretim çağrıları oluşur."
    ),
    "a1.section.record": "2. Kayıt",
    "a1.record_button": "Turu Çek",
    "a1.recording_status": "Tur kaydediliyor…",
    "a1.stage.voice": "Seslendirme kontrol ediliyor",
    "a1.stage.server": "Uygulama başlatılıyor",
    "a1.stage.open": "Tarayıcı açılıyor",
    "a1.stage.thinking": "Adım {step}: ajan karar veriyor",
    "a1.stage.acting": "Adım {step}: {message}",
    "a1.stage.invalid": "Adım {step} geçersiz: {message}",
    "a1.stage.retry": "Adım {step} yeniden deneniyor: {message}",
    "a1.stage.done": "Ajan turu tamamladı",
    "a1.stage.render": "Video işleniyor",
    "a1.stage.finished": "Tamamlandı",
    "a1.stage.error": "Hata",
    "a1.section.result": "3. Sonuç",
    "a1.result_none": "Henüz bir tur çekilmedi. Yukarıdan 'Turu Çek' butonuna basın.",
    "a1.result_video_missing": "Video dosyası üretilemedi. Nedeni: {reason}",
    "a1.metric.steps": "Adım sayısı",
    "a1.metric.duration": "Süre (sn)",
    "a1.metric.cost": "Tahmini maliyet",
    "a1.metric.voiced": "Seslendirme",
    "a1.voiced_yes": "Var",
    "a1.voiced_no": "Yok",
    "a1.stopped_reason_label": "Turun bitiş nedeni:",
    "a1.download_subtitle": "Altyazıyı indir (.srt)",
    "a1.download_video": "Videoyu indir",
    "a1.section.steps": "Ajanın adımları",
    "a1.steps_caption": (
        "Ajanın her adımda ne yaptığı ve NEDEN yaptığı — şeffaflık için "
        "modelin kendi gerekçesiyle birlikte."
    ),
    "a1.step_column.index": "Adım",
    "a1.step_column.action": "Eylem",
    "a1.step_column.target": "Hedef",
    "a1.step_column.narration": "Anlatım",
    "a1.step_column.reason": "Gerekçe",
    "a1.section.library": "Önceki Kayıtlar",
    "a1.library_empty": "Henüz kaydedilmiş bir tur videosu yok.",
    "a1.library_stale": "Kaynak kod bu kayıttan sonra değişti — tur yeniden çekilebilir.",
    "a1.library_fresh": "Kaynak kodla güncel.",
    "a1.playwright_missing": (
        "Playwright kurulu değil. Kurmak için: `pip install playwright` ve "
        "ardından `playwright install chromium`."
    ),
    "a1.ffmpeg_missing": (
        "FFmpeg bulunamadı. Video MP4'e çevrilemez ve altyazı gömülemez; "
        "ham kayıt yine de sunulur."
    ),
    "a1.driver_label": "Sürücü model",
    "a1.driver_note": (
        "Ajan her adımda ekran görüntüsüne bakıp tek bir karar verdiği için "
        "burada iki modelli karşılaştırma yoktur — tek aktif sürücü kullanılır."
    ),
}

EN = {
    "a1.page_subtitle": "A1 — Automatic Product Tour Studio",
    "a1.page_caption": (
        "A visual AI agent navigates the running application on its own: at "
        "every step it looks at the screen, decides where to click, moves the "
        "cursor there, and records the whole session as a video. The narration "
        "is burned in as subtitles and voiced with Amazon Polly if configured."
    ),
    "a1.how_it_works_title": "How does this work?",
    "a1.how_it_works_body": (
        "**1. The app is launched** — the application being recorded runs as "
        "its own process on a separate port, so this page is unaffected.\n\n"
        "**2. The agent looks at the screen** — at every step a real "
        "screenshot is taken and the real interface elements (buttons, "
        "fields, tabs) are read from the browser itself.\n\n"
        "**3. The agent decides** — the visual model sees the current screen "
        "and decides on a single next step. There is no pre-written script; "
        "the agent proceeds by seeing the result of its previous step.\n\n"
        "**4. The decision is checked** — a deterministic check confirms the "
        "chosen element actually exists on screen. This prevents the cursor "
        "from clicking empty space; it does not constrain the agent's "
        "freedom to decide.\n\n"
        "**5. The cursor moves and is recorded** — the cursor glides to the "
        "target, clicks, and waits until Streamlit has finished its work."
    ),
    "a1.section.settings": "1. Recording Settings",
    "a1.module_label": "Module to tour",
    "a1.language_label": "Tour language",
    "a1.max_steps_label": "Maximum number of steps",
    "a1.max_steps_help": (
        "Every step is one visual model call. If the agent finishes the tour "
        "earlier, this limit is never reached."
    ),
    "a1.enable_voice_label": "Voice with Amazon Polly",
    "a1.enable_voice_help": (
        "If turned off, the video is produced silent but with subtitles. If "
        "Polly is not configured it already falls back to silent automatically."
    ),
    "a1.voice_ready": "Voiceover ready: {detail}",
    "a1.voice_unavailable": "Voiceover unavailable: {detail} — the video will be silent but subtitled.",
    "a1.cost_warning": (
        "**Cost warning:** While recording, the agent uses the real "
        "interface; if it presses a generate button, that module's real "
        "model calls are triggered too. Each recording costs roughly {steps} "
        "visual model calls plus any triggered generation calls."
    ),
    "a1.section.record": "2. Recording",
    "a1.record_button": "Record Tour",
    "a1.recording_status": "Recording the tour…",
    "a1.stage.voice": "Checking voiceover",
    "a1.stage.server": "Starting the application",
    "a1.stage.open": "Opening the browser",
    "a1.stage.thinking": "Step {step}: the agent is deciding",
    "a1.stage.acting": "Step {step}: {message}",
    "a1.stage.invalid": "Step {step} invalid: {message}",
    "a1.stage.retry": "Retrying step {step}: {message}",
    "a1.stage.done": "The agent completed the tour",
    "a1.stage.render": "Processing the video",
    "a1.stage.finished": "Finished",
    "a1.stage.error": "Error",
    "a1.section.result": "3. Result",
    "a1.result_none": "No tour recorded yet. Press 'Record Tour' above.",
    "a1.result_video_missing": "The video file could not be produced. Reason: {reason}",
    "a1.metric.steps": "Step count",
    "a1.metric.duration": "Duration (s)",
    "a1.metric.cost": "Estimated cost",
    "a1.metric.voiced": "Voiceover",
    "a1.voiced_yes": "Yes",
    "a1.voiced_no": "No",
    "a1.stopped_reason_label": "Why the tour ended:",
    "a1.download_subtitle": "Download subtitles (.srt)",
    "a1.download_video": "Download video",
    "a1.section.steps": "The agent's steps",
    "a1.steps_caption": (
        "What the agent did at every step and WHY — including the model's own "
        "reasoning, for transparency."
    ),
    "a1.step_column.index": "Step",
    "a1.step_column.action": "Action",
    "a1.step_column.target": "Target",
    "a1.step_column.narration": "Narration",
    "a1.step_column.reason": "Reason",
    "a1.section.library": "Previous Recordings",
    "a1.library_empty": "No tour videos recorded yet.",
    "a1.library_stale": "The source code changed after this recording — the tour can be re-recorded.",
    "a1.library_fresh": "Up to date with the source code.",
    "a1.playwright_missing": (
        "Playwright is not installed. To install: `pip install playwright` "
        "then `playwright install chromium`."
    ),
    "a1.ffmpeg_missing": (
        "FFmpeg was not found. The video cannot be converted to MP4 and "
        "subtitles cannot be burned in; the raw recording is still provided."
    ),
    "a1.driver_label": "Driver model",
    "a1.driver_note": (
        "Because the agent looks at a screenshot and makes a single decision "
        "at each step, there is no two-model comparison here — a single "
        "active driver is used."
    ),
}
