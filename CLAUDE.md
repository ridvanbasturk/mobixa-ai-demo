# CLAUDE.md

Bu dosya, bu repoda çalışırken Claude Code için bağlam sağlar.

## Proje

Mobixa AI Demo — Amazon Bedrock üzerindeki model çiftlerini aynı girdi
ve prompt ile karşılaştırmalı çalıştıran bir Streamlit PoC uygulaması.
Aktif modüller: B1 (içerikten çoktan seçmeli soru + öğrenme kartı
üretimi, Qwen3/Gemma 4), B6 (rapor CSV'sinden deterministik metrik
hesaplama + yönetim değerlendirme kartı üretimi, Qwen3/Gemma 4), C1
(Journey talebi + gerçek aktivite kataloğundan otomatik Journey/öğrenme
yolu oluşturma, Qwen3/Gemma 4 — insan değerlendirmesi yok), A2 (destek/
onboarding chatbot, Gemma 4 varyantları — kendi model çifti, yerel
deterministik retrieval, insan değerlendirmesi yok) ve A1 (otomatik ürün
turu stüdyosu — görsel bir ajan çalışan uygulamayı GERÇEKTEN gezip video
kaydeder; tek sürücü model, insan değerlendirmesi yok).

C1'in veri modeli, yöneticinin paylaştığı gerçek "Client" uygulaması
Journey/aktivite yapısına dayanır: bir Journey, sıralı GAME/TEST/LEARN
tipinde aktivitelerden oluşur (S3'te journey-id → aktivite-klasörleri
şeklinde saklanır, her aktivitenin `activityId/activityType/
activitySubType/timeLimit/questionCount/questions` alanlarını içeren bir
JSON'u vardır). LEARN tipi aktiviteler S3'te değil DB'de tutulur; gerçek
şeması henüz paylaşılmadı. `sample_data/activity_catalog.csv`, hem
yöneticinin paylaştığı 6 gerçek aktiviteyi HEM DE başlığı "[Örnek Veri]"
ile başlayan 8 sentetik/illüstratif aktiviteyi (test hacmini artırmak ve
LEARN tipini de örneklemek için, `docs/Journey_Json_ve_ssler/SAMPLE-*.json`
dosyalarından) içerir — sentetik satırlar UI'da ve JSON dosyalarının
`_not_real_note` alanında açıkça işaretlidir, gerçek Mobixa verisiyle asla
karıştırılmamalıdır (bkz. `scripts/build_activity_catalog.py` docstring'i).

## Mimari

- `app.py` — ince giriş noktası; yalnızca `st.navigation`/`st.Page` ile
  modül listesini tanımlar. Sayfa mantığı içermez.
- `app_pages/b1_content_generation.py` — B1'in tüm Streamlit mantığı
  (sidebar, içerik girişi, üretim, model kartları, karşılaştırma
  özeti, insan değerlendirmesi).
- `app_pages/b6_report_insights.py` — B6'nın tüm Streamlit mantığı;
  B1'dekiyle aynı desende sidebar/üretim/karşılaştırma/insan
  değerlendirmesi, ek olarak CSV önizleme, hesaplanan metrik kartları,
  risk grupları ve rakamsal kontrol göstergesi.
- `app_pages/c1_learning_path.py` — C1'in tüm Streamlit mantığı; aynı
  desen (sidebar/üretim/karşılaştırma), ancak **insan değerlendirmesi
  bölümü yok**. Girdi bir Journey talebi (brief: hedef kitle, amaç,
  zorunlu konular, min/max aktivite sayısı, sınavla bitme zorunluluğu)
  ve bir aktivite kataloğudur; çıktı yalnızca kataloğa dayalı, sıralı
  bir Journey önerisidir. Deterministik iş kuralı doğrulaması
  (`validate_business_rules`) sonucu gösterilir.
- `app_pages/a2_support_chatbot.py` — A2'nin tüm Streamlit mantığı; 3
  sekme (Chatbot / Bilgi Tabanı / Yetenekler ve Entegrasyonlar). Sohbet
  sekmesi gerçek bir chatbot gibi görünecek şekilde tasarlanmıştır:
  `st.chat_message`/`st.chat_input` ile karşılama balonu + öneri çipleri
  (yalnızca geçmiş boşken) + kronolojik sohbet akışı; varsayılan
  görünüm yalnızca birincil modelin (Plan A) dostça bir yanıtını
  gösterir (kaynak atıfı + gerekirse yönlendirme notu), ham
  token/maliyet/doğrulama detayları ve iki-model karşılaştırması
  kapalı bir **"Teknik detaylar"** expander'ına taşınmıştır. İkinci
  model yalnızca sohbetin üstündeki **"Karşılaştırma Modu"** anahtarı
  açıkken çağrılır (varsayılan kapalı — daha hızlı/ucuz). Sohbet
  geçmişi `session_state.a2_chat_history` listesinde tutulur, her tur
  kendi `comparison_mode` durumunu da saklar. **İnsan değerlendirmesi
  yok.**
- `app_pages/a1_tour_studio.py` — A1'in tüm Streamlit mantığı (otomatik
  ürün turu stüdyosu). Yalnızca ARAYÜZDÜR; ağır iş
  `services/tour_*.py` içindedir. Diğer modüllerden iki yapısal farkı
  vardır: **iki modelli karşılaştırma YOK** (ajan her adımda tek karar
  verir, aynı turu iki modelle sürmek karşılaştırılabilir bir şey
  üretmez) ve **insan değerlendirmesi YOK** (çıktı metin değil video;
  şeffaflık adım dökümüyle sağlanır).
  `services/module_placeholder.py`, henüz geliştirilmemiş gelecekteki
  modüller için hâlâ kullanılabilir tek satırlık placeholder deseni
  sağlar.

### A1 tur boru hattı (`services/tour_*.py`)

Ajan her adımda ekran görüntüsüne bakıp TEK bir karar verir; önceden
yazılmış senaryo yoktur. Piksel koordinatı tahmin ettirmek yerine canlı
DOM'dan çıkarılan gerçek öğe envanterinden seçtirilir — canlı sürme
korunur, imleç asla boşluğa tıklamaz.

- `tour_app_server.py` — kaydedilecek uygulamayı AYRI bir portta alt
  süreç olarak başlatır (`/_stcore/health` beklenir). Stüdyo sayfası da
  bir Streamlit sayfası olduğu için ayrı süreç şarttır.
- `tour_dom_inspector.py` — canlı DOM'dan etkileşimli öğe envanteri
  (rol, görünen ad, `st-key`, konum, sidebar mı, **offscreen mı**).
  Ekran dışı öğeler ELENMEZ; elenirse uzun sayfalarda asıl eylem butonu
  ajana hiç görünmez.
- `tour_cursor.py` — videoda görünen yapay imleç (Playwright gerçek
  imleci kaydetmez) + tıklama dalgası + vurgu çerçevesi.
- `tour_agent_service.py` — karar katmanı; Streamlit/Playwright'tan
  bağımsız, sahte `call_model` ile test edilebilir. Set-of-Mark:
  görüntünün KOPYASINA numaralı rozetler basılır (videoya girmez).
- `tour_validation.py` — kararın deterministik denetimi. İmza
  konumsal indeksle DEĞİL öğe kimliğiyle (`st-key`/ad) kurulur; indeksle
  kurulursa sayfa değiştikçe numaralar kayar ve döngü fark edilmez.
- `tour_tts.py` — takılabilir seslendirme: `PollyTTS` + `NullTTS`.
  Polly kimlik bilgisi yoksa ÇÖKMEZ, sessiz+altyazılı videoya düşer.
- `tour_video_service.py` — FFmpeg: webm→mp4, adım seslerini `adelay`
  ile kendi zamanına yerleştirip `amix`, libass ile altyazı gömme.
- `tour_pipeline.py` — uçtan uca orkestrasyon (`run_tour`). Metin
  girişinde `keyboard.type()` DEĞİL `fill()` kullanılır: Streamlit'in
  React kontrollü `st.chat_input`'ı sentetik tuş olaylarını değer olarak
  kaydetmez.
- `scripts/record_tour.py` — aynı `run_tour`'u CLI'dan çağırır.
- `services/i18n.py` + `services/i18n_strings/{common,b1,b6,c1,a2,a1}.py`
  — uygulama genelinde TR/EN dil desteğinin tek kaynağı. Dil seçimi
  `st.session_state["app_language"]` üzerinden tüm sayfalar arasında
  paylaşılır; `render_language_switcher()` her sayfanın en üstünde sağa
  yaslanmış bir TR/EN segmented control render eder, `t(key)` geçerli
  dile göre çeviri döner (eksik anahtar TR'ye, o da yoksa anahtarın
  kendisine düşer — sessizce yutulmaz). `tests/test_i18n.py`, TR/EN
  sözlüklerinin anahtar kümesinin birebir eşleştiğini doğrular.
  **Kapsam dışı (bilinçli sınırlama):** Pydantic/iş kuralı ham hata
  mesajları (`schemas/*.py`, `validate_business_rules` vb.) TÜM
  modüllerde Türkçe kalır — hem şemaların Streamlit'ten bağımsız kalması
  hem de bu mesajların tam TR metnini `assert` eden çok sayıda testin
  kırılmaması için. A1'in vision/sahne genişletme alt akışı da (4 prompt
  dosyası + ilgili UI) henüz çevrilmedi, bkz. `services/i18n_strings/a1.py`
  docstring'i.
- `services/bedrock_client.py` — OpenAI SDK ile Bedrock Mantle uç
  noktasına çağrı yapar (`call_model`), hataları Türkçe sınıflandırır,
  token/gecikme/maliyet toplar. `ModelCallResult.api_call_success` ve
  `error_category` alanları, JSON ayrıştırmadan bağımsız olarak
  bağlantı durumunu (`next_connection_status`) belirlemek için vardır.
  `CONNECTION_STATUS_LEVELS`/`CONNECTION_MESSAGE_KEYS`, bağlantı durumu
  mesajlarının render seviyesini ve i18n anahtarını taşır (metnin kendisi
  `services/i18n_strings/common.py`'dedir). İki doğrulanmış model-uyum
  düzeltmesi (ikisi de "openai" rotasındaki bir Gemma varyantıyla canlı
  test edilerek keşfedildi): (1) rotaya göre `max_tokens` yerine
  `max_completion_tokens` gönderilir, (2) bazı modeller yalnızca
  varsayılan `temperature` (1) değerini kabul eder — bu durum HTTP 400
  hata metninden (`_is_fixed_temperature_error`) tespit edilip
  `temperature` parametresi tamamen atlanarak TEK SEFER otomatik
  yeniden denenir. İkisi de `call_model` içinde, tüm modülleri kapsar.
- `services/json_parser.py` — model çıktısını JSON'a çevirmek için
  5 aşamalı fallback zinciri (`json.loads` → markdown temizleme →
  brace extraction → `json_repair`).
- `services/cost_calculator.py` — `config/model_prices.json`
  üzerinden tahmini maliyet hesaplar; token yoksa `None` döner.
- `services/document_parser.py` — TXT/PDF/DOCX/PPTX metin çıkarma.
- `services/evaluation_logger.py` — her model çağrısını `run_id` ile
  `outputs/evaluations.csv` dosyasına ekler; eski şemalı CSV
  dosyalarını otomatik göç ettirir (`_migrate_csv_if_needed`);
  `save_human_evaluation` insan değerlendirmesini aynı `run_id`
  satırına yazar.
- `services/comparison.py` — yalnızca ölçülebilir teknik verilere
  (maliyet, gecikme, token, JSON/şema geçerliliği) dayalı karşılaştırma
  mesajları üretir; anlamsal kalite iddiası yapmaz.
- `services/model_registry.py` — Plan A/Plan B başlık ve alt başlıkları
  için tek kaynak. `PLAN_A`/`PLAN_B` = B1/B6/C1'in Qwen3/Gemma 4 çifti;
  `A2_PLAN_A`/`A2_PLAN_B` = A2'nin ayrı Gemma 4 varyant çifti (env:
  `A2_MODEL_A`/`A2_MODEL_B`). Bu ikisi birbirinin yerine geçmez.
  `PlanInfo.slot_label_for(lang)`/`subtitle_for(lang)`/`heading_for(lang)`
  i18n-farkındalıklı erişim sağlar; `display_name` (model adı) kasıtlı
  olarak dilden bağımsızdır.
- `services/report_service.py` — B6 için deterministik metrik
  hesaplama (`load_and_validate_report`, `compute_report_metrics`) ve
  rakamsal doğrulama (`validate_numeric_grounding`, Türkçe ondalık
  virgülü destekli). Tüm aritmetik burada yapılır; modele yalnızca
  hesaplanmış metrik JSON'u gönderilir.
- `services/learning_path_service.py` — C1 için Journey talebi (brief)/
  aktivite kataloğu doğrulama (`load_and_validate_journey_brief`,
  `load_and_validate_catalog`) ve deterministik iş kuralı doğrulaması
  (`validate_business_rules`): katalogda bulunmayan/hariç tutulması
  gereken/tekrarlanan aktivite, süre tutarsızlığı, min/max aktivite
  sayısı sınırı, zorunlu konu kapsamı, `must_end_with_test` (Journey'in
  bir TEST tipi aktiviteyle bitmesi) kuralı. Model çıktısını gizlemez,
  yalnızca bir doğrulama raporu (errors/warnings) üretir.
- `scripts/build_activity_catalog.py` — yöneticinin paylaştığı gerçek
  aktivite JSON export'larından (varsayılan girdi dizini:
  `docs/Journey_Json_ve_ssler/`) `sample_data/activity_catalog.csv`
  dosyasını türetir; yalnızca üst seviye metadata okur (soru içerikleri
  kataloğa yazılmaz), hiçbir alan uydurmaz. Yeni JSON'lar paylaşıldıkça
  tekrar çalıştırılabilir.
- `services/a2_retrieval_service.py` — A2 için yerel, deterministik
  sözcük temelli (lexical) retrieval. Bedrock Knowledge Bases, vektör
  veritabanı veya embedding KULLANMAZ; yalnızca onaylı (`status ==
  "approved"`) kayıtları getirir. `language="tr"` (varsayılan) Türkçe-
  farkındalıklı normalize (prefix eşleştirme ile ek varyasyonlarını
  tolere eder), `language="en"` düz küçük harf + küçük bir EN stopword
  listesi kullanır. Eşik altı kalırsa boş bağlam + `sufficient=False`
  döner — model çağrısı bundan bağımsız olarak yapılır ama kaynaksız
  kalır. TR/EN bilgi tabanları ayrı dosyalardır: `sample_data/
  a2_knowledge_base.json` (TR) / `a2_knowledge_base_en.json` (EN, aynı
  22 kaydın çevirisi, id'ler birebir eşleşir) — sayfa hangi dosyanın
  yükleneceğine `get_language()`'a göre karar verir. **Bu 22 kayıt
  TAMAMEN sentetik/placeholder'dır** (gerçek wiki dosyası henüz
  paylaşılmadı); yönetici gerçek dosyayı gönderdiğinde bu iki JSON'un
  içeriği birebir gerçek veriyle DEĞİŞTİRİLECEK — kod tarafında hiçbir
  değişiklik gerekmez, dosyalar zaten yoldan okunuyor.
- `services/a2_validation.py` — dayanak (grounding) doğrulaması
  (`validate_grounding`: bilinmeyen kaynak ID, sahte destek kanalı,
  uydurma "299 TL", sistem promptu ifşası — refüzü değil, "kesin yokluk
  iddiası" tespiti) ve deterministik escalation kararı
  (`compute_final_escalation`). Modelin escalation önerisine tek
  başına güvenilmez.
- `services/a2_skill_registry.py` — aktif PoC yetenekleri, gelecek
  plugin listesi ve tek bir güvenli simülasyon; `get_active_skills(lang)`
  /`get_future_plugins(lang)`/`get_activity_status(activity_id, lang)`
  ile TR/EN döner (`get_activity_status` her zaman sabit örnek veri +
  "Simülasyon"/"Simulation" etiketiyle döner).
- `services/a2_chat_service.py` — A2 model çağrısı orkestrasyonu
  (Streamlit'ten bağımsız, `run_chat_turn(..., language="tr")`);
  B1/B6/C1'in aksine bu mantık sayfa dosyası yerine ayrı bir serviste
  çünkü sohbet akışında tekrar tekrar çağrılıyor. `build_user_prompt`
  içindeki sabit etiketler de `language` parametresine göre TR/EN seçilir.
- `schemas/b1_models.py` / `schemas/b6_models.py` / `schemas/c1_models.py`
  / `schemas/a2_models.py` — Pydantic şemaları + yapısal doğrulama.
- `prompts/{b1,b6,c1,a2}_system.txt` + `prompts/tour_agent_system.txt`
  (TR) ve aynı isimlerin `_en.txt` sürümleri (EN) — özelliğe özgü sistem
  promptları; sayfalar `load_system_prompt(language)` ile doğru dosyayı
  seçer.

## Kurallar

- API anahtarı asla kaynak koda yazılmaz, loglanmaz veya yazdırılmaz.
- `.env` dosyası oluşturulmaz/okunmaz; yalnızca `.env.example` vardır.
- Bir modelin hatası diğer modelin çağrısını engellemez —
  `run_model_and_validate` her model için bağımsız çalışır.
- Token bilgisi API'den gelmezse maliyet hesaplanmaz; token uydurulmaz.
- B1/B6/C1/A2 (ve A1'in ana sayfa/sidebar kabuğu) TR/EN dil desteklidir
  (bkz. `services/i18n.py`). Ham Pydantic/iş kuralı hata mesajları ve
  A1'in vision/sahne genişletme alt akışı bu kapsamın dışındadır ve
  daima Türkçedir (bkz. yukarıdaki i18n kapsam notu) — yeni bir
  kullanıcıya-dönük metin eklerken varsayılan olarak `t()`/i18n
  sözlüklerine eklenmelidir, doğrudan hardcoded TR/EN string yazılmamalı.
- Bağlantı durumu (`connection_status`) yalnızca `api_call_success`
  veya `auth`/`connection` kategorili hatalarla güncellenir; rate limit
  gibi diğer hatalar mevcut durumu değiştirmez.

## Test

```
pytest                          # birim testler (gerçek API çağrısı yapmaz)
python scripts/smoke_test.py    # gerçek Bedrock bağlantı testi
```

## Sonraki aşama

**A1 — kod değişince videoların otomatik yenilenmesi (KAPSAM DIŞI):**
Kullanıcı bunun gerçek uygulamaya entegrasyonda gerekeceğini belirtti;
bu turda yalnızca BAĞLANTI NOKTASI hazırlandı. Her kaydın yanına
`<modül>_<dil>.meta.json` içinde `source_fingerprint` yazılıyor
(`tour_pipeline.compute_source_fingerprint`) ve stüdyo sayfası
"bayat/güncel" rozetini bununla gösteriyor. Eksik olan yalnızca
TETİKLEME mekanizması (git hook / CI / izleyici) — parmak izi
karşılaştırması zaten çalışıyor.

**A1 seslendirme:** Polly katmanı yazıldı ve test edildi ama makinede
`boto3` kurulu DEĞİL ve `.env`'de AWS erişim anahtarı yok; bu yüzden
videolar şu an sessiz+altyazılı üretiliyor ve neden arayüzde açıkça
yazıyor. `pip install boto3` + AWS kimlik bilgileri eklenince ek kod
gerekmeden devreye girer.

**TR/EN i18n — kalan kapsam:** tüm modüllerdeki ham Pydantic/iş kuralı
hata mesajları hâlâ Türkçedir (şemaların Streamlit'ten bağımsız kalması
gereken mimarisiyle çelişmeden nasıl çevrileceği ayrıca düşünülmeli —
ör. hata kodu döndürüp render katmanında çevirmek gibi).

C1'in örnek aktivite kataloğu şu an yalnızca yöneticinin paylaştığı 6
gerçek aktiviteyi içeriyor (`scripts/build_activity_catalog.py` ile
türetildi). Yönetici daha fazla aktivite JSON'u (özellikle LEARN tipi,
hiç örneği yok) paylaştıkça script'i tekrar çalıştırıp kataloğu
büyütmek yeterli. Yeni bir modül etkinleştirirken ilgili
`app_pages/<modül>.py` dosyasını `render_placeholder(...)` çağrısı
yerine gerçek mantıkla değiştir; yeni bir `prompts/<feature>_system.txt`
ve `schemas/<feature>_models.py` oluşturmak yeterli olmalı —
`bedrock_client.py`, `evaluation_logger.py` ve `comparison.py` genel
amaçlı kalmalı. `evaluation_logger.FIELDNAMES`
ve `save_human_evaluation` zaten özellik-agnostik biçimde (yalnızca
None olmayan alanları yazan) tasarlandı; yeni bir modül kendi insan
değerlendirme alanlarını benzer şekilde ekleyebilir (C1'de olduğu gibi
insan değerlendirmesi hiç gerekmiyorsa bu adım tamamen atlanabilir).
`services/comparison.py::ModelMetrics.business_valid` alanı da
opsiyoneldir; yalnızca deterministik iş kuralı doğrulaması yapan
modüller (C1 gibi) doldurur.
