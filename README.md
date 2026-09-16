# Mobixa AI Demo

Amazon Bedrock Mantle modellerini kullanan, Türkçe/İngilizce arayüzlü
yerel Streamlit uygulaması. Beş AI modülünün kaynak kodları, promptları,
şemaları, örnek verileri ve testleri bu repoda bulunur.

| Modül | İşlev |
| --- | --- |
| B1 | Metin, PDF, DOCX ve PPTX içeriğinden soru ve öğrenme kartı üretimi |
| B6 | Rapor CSV'sinden metrik hesaplama ve yönetim değerlendirmesi |
| C1 | Aktivite kataloğundan Journey oluşturma, doğrulama ve oluşturma paketi indirme |
| A2 | Yerel bilgi tabanına dayalı destek/onboarding chatbot |
| A1 | Görsel ajanın uygulamayı gezerek otomatik ürün turu videosu üretmesi |

B1/B6/C1 için varsayılan model çifti Qwen3/Gemma 4'tür. A2 Gemma
varyantlarını, A1 tek görsel sürücü modeli kullanır. Model ve servis
ayarları `.env.example` ve `services/model_registry.py` içindedir.
Hesabınızın ilgili modellere erişimi olmalıdır.

## Diğer bilgisayarda kurulum

Git ve Python 3.11 kurun. Özel repoyu klonlamak için GitHub hesabınızla
kimlik doğrulaması gerekir:

```sh
git clone https://github.com/ridvanbasturk/mobixa-ai-demo.git
cd mobixa-ai-demo
```

### Sanal ortam ve bağımlılıklar

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

macOS/Linux:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Linux'ta Chromium sistem bağımlılıkları eksikse
`python -m playwright install --with-deps chromium` çalıştırın.
Windows'ta aşağıdaki `python` komutları için
`.\.venv\Scripts\python.exe` kullanın; sanal ortamı etkinleştirmek zorunlu değildir.

### FFmpeg (video üretimi için)

`ffmpeg` ve `ffprobe` PATH üzerinde erişilebilir olmalıdır.
FFmpeg dağıtımında `libx264` ve `subtitles`/libass desteği bulunmalıdır.

Windows:

```powershell
winget install --id Gyan.FFmpeg --exact
```

macOS (Homebrew):

```sh
brew install ffmpeg
```

Ubuntu/Debian:

```sh
sudo apt-get update
sudo apt-get install ffmpeg
```

Terminali yeniden açıp kurulumu kontrol edin:

```sh
ffmpeg -version
ffprobe -version
```

### API ve seslendirme ayarları

Yeni bilgisayardaki `.env` dosyasına Bedrock Mantle anahtarınızı
`OPENAI_API_KEY` olarak girin. Mevcut bilgisayarda değiştirdiğiniz model,
endpoint veya bölge ayarlarını da taşıyın. `.env` GitHub'a yüklenmez;
anahtarları güvenli bir kanaldan aktarın veya yeniden tanımlayın.

Sesli video için Amazon Polly ayrıca AWS kimlik bilgileri ister:
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` ve geçici kimlik bilgileri
kullanılıyorsa `AWS_SESSION_TOKEN`. AWS profiliniz varsa boto3'ün standart
kimlik bilgisi zinciri de kullanılabilir. Polly, Bedrock API anahtarını
kullanmaz. Bölge ve ses tercihleri `.env.example` içinde açıklanmıştır.

Polly erişimi olmadığında video sessiz ve altyazılı üretilir.
Seslendirme erişimini doğrulamak için (gerçek AWS çağrısı yapar):

```sh
python scripts/check_polly.py --sample
```

### Uygulamayı çalıştırma

```sh
python -m streamlit run app.py
```

Varsayılan adres: `http://localhost:8501`. Sol menüde beş modül bulunur.

## Otomatik video oluşturma

A1 Ürün Turu Stüdyosu ayrı bir yerel Streamlit süreci başlatır.
Görsel ajan ekran görüntüsü ve DOM öğeleri üzerinden uygulamayı canlı
gezer. Playwright kaydı, Polly seslendirmesi ve FFmpeg ile altyazılı MP4
üretimi aynı akışta çalışır. Arayüzden veya CLI'dan başlatılabilir:

```sh
python scripts/record_tour.py --list
python scripts/record_tour.py --module c1 --lang tr
python scripts/record_tour.py --module a2 --lang en --max-steps 12
python scripts/record_tour.py --module c1 --lang tr --no-voice
```

Kayıtlar `outputs/tour_videos/` altında MP4, SRT altyazı, adım dökümü ve
metadata olarak saklanır. Bu üretilmiş dosyalar Git'e dahil değildir;
eski kayıtları da taşımak için bu klasörü ayrıca aktarın.
Yerel `outputs/evaluations.csv` geçmişi de Git'e dahil değildir.

Kod değişikliklerinde kayıtların güncelliği kaynak parmak iziyle
denetlenir. Kod değişince kendiliğinden kayıt başlatan CI/git hook/izleyici
henüz yoktur; kayıt arayüzden veya yukarıdaki komutlarla tetiklenir.
Video üretimi ve uygulamadaki AI işlemleri gerçek model çağrıları yapar.

## Testler

```sh
python -m pytest -q
```

Birim testler gerçek Bedrock çağrısı yapmaz. İsteğe bağlı bağlantı testi
`python scripts/smoke_test.py` ile çalıştırılır; bu komut gerçek API
istekleri gönderir ve `TEXT_MODEL_A`/`TEXT_MODEL_B` ayarlarını kullanır.

## Geliştirmeye devam etme

Bir bilgisayardaki çalışmayı diğerine geçmeden önce gönderin:

```sh
git add .
git commit -m "Describe the change"
git push
```

Diğer bilgisayarda çalışmaya başlamadan önce:

```sh
git pull --ff-only
```

Bağımlılıklar değişmişse `python -m pip install -r requirements.txt`
komutunu yeniden çalıştırın. Sanal ortam, Chromium ve FFmpeg her
bilgisayara ayrı kurulur; `.env` ve AWS kimlik bilgileri ayrıca tanımlanır.

## Dosya yapısı ve sınırlar

- `app.py`, `app_pages/`: giriş noktası ve beş modülün arayüzleri.
- `services/`: model çağrıları, doğrulama, chatbot ve video üretim hattı.
- `schemas/`, `prompts/`, `config/`: şemalar, TR/EN promptlar ve maliyet ayarları.
- `sample_data/`, `docs/`: örnek girdiler, aktivite exportları ve proje belgeleri.
- `scripts/`, `tests/`: CLI araçları ve otomatik testler.
- `CLAUDE.md`: mimari ve mevcut geliştirme bağlamı.

Bu uygulama yerel bir PoC'dir. C1 oluşturma paketini üretir, gerçek S3/DB'ye
yazmaz. A2 bilgi tabanındaki örnek içerikler ve katalogdaki `[Örnek Veri]`
aktiviteleri sentetiktir. OCR, kullanıcı yönetimi ve production deployment
mevcut kapsamın dışındadır. Python bağımlılıkları minimum sürüm sınırlarıyla
tanımlıdır; birebir sürüm kilidi bulunmaz.
