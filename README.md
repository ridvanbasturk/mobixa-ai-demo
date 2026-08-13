# Mobixa AI Demo — B1 İçerik Üretimi

Amazon Bedrock üzerindeki iki farklı modeli (Qwen3 Next 80B ve
DeepSeek V3.2) aynı eğitim içeriği ve aynı prompt ile çalıştırıp
üretilen çoktan seçmeli soruları ve öğrenme kartlarını yan yana
karşılaştıran bir Streamlit PoC uygulamasıdır.

Bu bir production uygulaması değildir — yerel makinede çalışan,
temiz bir kanıt niteliğinde (Proof of Concept) uygulamadır.

## Kurulum

### 1. Python 3.11 kurulumu

Python 3.11'in sisteminizde kurulu olduğundan emin olun:

```
python --version
```

Kurulu değilse [python.org](https://www.python.org/downloads/) üzerinden
Python 3.11 indirip kurun.

### 2. Sanal ortam oluşturma

```
python -m venv .venv
```

Windows'ta etkinleştirme:

```
.venv\Scripts\activate
```

macOS/Linux'ta etkinleştirme:

```
source .venv/bin/activate
```

### 3. Bağımlılıkların kurulumu

```
pip install -r requirements.txt
```

### 4. .env dosyasının oluşturulması

`.env.example` dosyasını `.env` olarak kopyalayın:

```
copy .env.example .env      (Windows)
cp .env.example .env        (macOS/Linux)
```

`.env` dosyasını açıp `OPENAI_API_KEY` alanına Bedrock Mantle API
anahtarınızı yazın:

```
OPENAI_API_KEY=<sizin-anahtarınız>
```

`.env` dosyası `.gitignore` içinde olduğu için git'e commit edilmez.
Anahtarınızı asla kaynak koda veya versiyon kontrolüne eklemeyin.

## Çalıştırma

### Streamlit uygulamasını başlatma

```
streamlit run app.py
```

Tarayıcıda açılan adresten (varsayılan `http://localhost:8501`)
uygulamaya erişebilirsiniz.

### Bağlantı duman testi

```
python scripts/smoke_test.py
```

Bu script API anahtarının çalışıp çalışmadığını, iki modele de kısa
birer istek göndererek doğrular. Anahtar değerini hiçbir zaman ekrana
yazdırmaz.

### Unit testlerin çalıştırılması

```
pytest
```

Testler gerçek Bedrock çağrısı yapmaz; maliyet formülü, JSON
ayrıştırma/onarma ve Pydantic doğrulama kurallarını kontrol eder.

## Demo kullanım sırası

1. Uygulamayı başlatın (`streamlit run app.py`).
2. Sol panelde API anahtarının bulunduğunu ve model kimliklerini
   kontrol edin.
3. Ana ekranda bir içerik kaynağı seçin: metin yapıştırın, bir dosya
   yükleyin (TXT/PDF/DOCX/PPTX) ya da hazır örnek metni kullanın.
4. Soru sayısını, zorluk seviyesini ve öğrenme kartı seçeneğini
   ayarlayın.
5. "İki Modelle Üret" butonuna tıklayın.
6. Model A (Qwen3) ve Model B (DeepSeek) sonuçları yan yana iki
   sütunda görünür: token sayıları, gecikme, tahmini maliyet, JSON
   geçerliliği, Pydantic doğrulama sonucu, üretilen sorular ve
   öğrenme kartları.
7. Her modelin ham çıktısını expander içinde inceleyebilir, JSON
   çıktısını indirebilirsiniz.
8. Sol panelden `outputs/evaluations.csv` dosyasını indirerek tüm
   çağrıların geçmiş kayıtlarını görebilirsiniz.

## Bilinen PoC sınırlamaları

- Model çağrıları paralel değil, sıralı çalışır (önce Model A, sonra
  Model B); çağrılar arasında kısa bir bekleme (throttling önlemi)
  uygulanır.
- OCR desteği yoktur; taranmış (görsel) PDF'lerden metin çıkarılamaz.
- Kullanıcı girişi, veritabanı ve Docker/AWS deployment bu aşamada
  yoktur.
- Fiyatlandırma bilgisi `config/model_prices.json` içinde sabit
  tanımlıdır ve Temmuz 2026 us-east-1 Standard fiyatlarına dayalı
  tahmini değerlerdir; gerçek faturalandırma AWS tarafından belirlenir.
- Token bilgisi API yanıtında yoksa maliyet hesaplanmaz ve arayüzde
  "Hesaplanamadı" olarak gösterilir; token uydurulmaz.
- Tüm test kayıtları tek bir yerel CSV dosyasına yazılır; eşzamanlı
  çoklu kullanıcı senaryosu için uygun değildir.

## Sonraki aşama

Bu PoC yalnızca B1 (içerikten soru/öğrenme kartı üretimi) kullanım
alanını kapsar. Sonraki aşamada B6, C1, A2 ve A1 özellikleri
eklenecektir. Kod yapısı bu genişlemeye uygun şekilde
(`services/`, `schemas/`, `prompts/` ayrımıyla) düzenlenmiştir.
