"""Tur videosunu komut satırından çeker (arayüz gerekmez).

Kullanım:
    python scripts/record_tour.py --module c1 --lang tr
    python scripts/record_tour.py --module a2 --lang en --max-steps 12
    python scripts/record_tour.py --module c1 --lang tr --no-voice
    python scripts/record_tour.py --list

Stüdyo sayfasıyla AYNI `run_tour` fonksiyonunu çağırır; iki yol arasında
davranış farkı yoktur.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows konsolu varsayılan olarak cp1254 kullanır ve Türkçe anlatım
# metinlerindeki karakterlerde (veya ok işaretinde) UnicodeEncodeError verir.
# Çıktıyı UTF-8'e çeviriyoruz; desteklenmiyorsa kodlanamayan karakterleri
# atmak yerine yerine koyuyoruz ki script asla bu yüzden çökmesin.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # noqa: PERF203 - eski Python/yönlendirilmiş çıktı
        pass

from dotenv import load_dotenv  # noqa: E402

from services.tour_pipeline import TOUR_MODULES, TourProgress, module_title, run_tour  # noqa: E402


def _print_progress(progress: TourProgress) -> None:
    prefix = f"[{progress.stage}]"
    if progress.step_index:
        prefix = f"[{progress.stage} #{progress.step_index}]"
    line = f"{prefix} {progress.message}".rstrip()
    print(line)
    if progress.narration:
        print(f"    → {progress.narration}")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--module", choices=sorted(TOUR_MODULES), help="Turu çekilecek modül")
    parser.add_argument("--lang", choices=["tr", "en"], default="tr", help="Tur dili")
    parser.add_argument("--max-steps", type=int, default=None, help="Maksimum adım sayısı")
    parser.add_argument("--model", default=None, help="Sürücü model kimliğini geçersiz kıl")
    parser.add_argument("--no-voice", action="store_true", help="Seslendirmeyi kapat (sessiz + altyazılı)")
    parser.add_argument("--list", action="store_true", help="Turu çekilebilecek modülleri listele")
    args = parser.parse_args()

    if args.list:
        for key in sorted(TOUR_MODULES):
            print(f"{key:4s}  {module_title(key, 'tr')}")
        return 0

    if not args.module:
        parser.error("--module gerekli (ya da --list kullanın)")

    recording = run_tour(
        module=args.module,
        language=args.lang,
        model_id=args.model,
        max_steps=args.max_steps,
        enable_voice=not args.no_voice,
        progress_callback=_print_progress,
    )

    print("")
    print(f"Adım sayısı      : {recording.step_count}")
    print(f"Süre             : {recording.total_seconds:.1f} sn")
    print(f"Seslendirme      : {'var' if recording.voiced else 'yok'}")
    if not recording.voiced and recording.voice_unavailable_reason:
        print(f"  (neden: {recording.voice_unavailable_reason})")
    print(f"Bitiş nedeni     : {recording.stopped_reason or '-'}")
    print(f"Video            : {recording.video_path or 'ÜRETİLEMEDİ'}")
    print(f"Altyazı          : {recording.subtitle_path or '-'}")

    return 0 if recording.video_path else 1


if __name__ == "__main__":
    raise SystemExit(main())
