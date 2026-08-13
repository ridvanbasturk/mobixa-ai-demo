"""Amazon Polly bağlantısını doğrular ve kullanılabilir sesleri listeler.

Kullanım:
    python scripts/check_polly.py            # bağlantı + ses listesi
    python scripts/check_polly.py --sample   # kısa bir deneme sesi üretir

`.env` içine AWS kimlik bilgilerini ekledikten sonra ÖNCE bunu çalıştırın:
tur kaydı başlatmadan (ve para harcamadan) seslendirmenin gerçekten
çalışıp çalışmadığını gösterir. Hiçbir kimlik bilgisi ekrana yazdırılmaz.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from dotenv import load_dotenv  # noqa: E402

from services.tour_tts import (  # noqa: E402
    DEFAULT_ENGINE_EN,
    DEFAULT_ENGINE_TR,
    DEFAULT_VOICE_EN,
    DEFAULT_VOICE_TR,
    PollyTTS,
)

SAMPLE_TR = "Merhaba, bu bir Mobixa ürün turu seslendirme denemesidir."
SAMPLE_EN = "Hello, this is a Mobixa product tour voiceover test."


def _print_voices(client, language_code: str, title: str) -> None:
    print(f"\n=== {title} ({language_code}) ===")
    try:
        voices = client.describe_voices(LanguageCode=language_code).get("Voices", [])
    except Exception as exc:  # noqa: BLE001
        print(f"  Listelenemedi: {type(exc).__name__}")
        return
    if not voices:
        print("  (bu dil için ses yok)")
        return
    for voice in voices:
        engines = ", ".join(voice.get("SupportedEngines", []))
        print(f"  {voice['Id']:12s} {voice.get('Gender', '?'):8s} motorlar: {engines}")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="Kısa bir deneme sesi üret (outputs/polly_test_*.mp3)")
    args = parser.parse_args()

    engine = PollyTTS()
    print(f"Bölge          : {engine.region}")
    print(f"Varsayılan TR  : {DEFAULT_VOICE_TR} ({DEFAULT_ENGINE_TR})")
    print(f"Varsayılan EN  : {DEFAULT_VOICE_EN} ({DEFAULT_ENGINE_EN})")
    print("")

    if not engine.available:
        print("SONUÇ: Polly KULLANILAMIYOR")
        print(f"  Neden: {engine.description}")
        print("")
        print("Yapılması gereken: .env dosyasına AWS kimlik bilgilerini ekleyin —")
        print("  AWS_ACCESS_KEY_ID=...")
        print("  AWS_SECRET_ACCESS_KEY=...")
        print("  # geçici (STS) kimlik bilgisi kullanıyorsanız ayrıca:")
        print("  # AWS_SESSION_TOKEN=...")
        print("  POLLY_REGION=eu-central-1")
        print("")
        print("Kimlik bilgisi eklenmezse tur videoları SESSİZ ama altyazılı üretilir.")
        return 1

    print(f"SONUÇ: Polly ÇALIŞIYOR — {engine.description}")

    client = engine._ensure_client()  # noqa: SLF001 - teşhis amaçlı bilinçli erişim
    _print_voices(client, "tr-TR", "Türkçe sesler")
    _print_voices(client, "en-US", "İngilizce sesler (en-US)")

    if args.sample:
        output_dir = Path(__file__).resolve().parent.parent / "outputs"
        print("\n=== Deneme sesleri üretiliyor ===")
        for language, text in (("tr", SAMPLE_TR), ("en", SAMPLE_EN)):
            path = output_dir / f"polly_test_{language}.mp3"
            result = engine.synthesize(text, language, path)
            if result.voiced:
                print(f"  {language}: {path} ({result.duration_seconds:.1f} sn)")
            else:
                print(f"  {language}: ÜRETİLEMEDİ — {result.error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
