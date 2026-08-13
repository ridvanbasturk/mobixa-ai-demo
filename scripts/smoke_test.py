"""Bedrock bağlantısını doğrulamak için basit duman testi.

API anahtarı yoksa anlaşılır bir uyarı verir. Anahtar değerini
hiçbir koşulda yazdırmaz.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from services.bedrock_client import call_model, is_api_key_configured

load_dotenv()

SYSTEM_PROMPT = "Sen kısa ve net yanıtlar veren bir yardımcı asistansın."
USER_PROMPT = "Yalnızca OK yaz."


def run_smoke_test(model_id: str, label: str) -> None:
    print(f"\n--- {label} ({model_id}) ---")
    result = call_model(model_id, SYSTEM_PROMPT, USER_PROMPT, temperature=0.0, max_tokens=20)

    if result.raw_text is not None:
        print(f"Yanıt: {result.raw_text.strip()}")
    if result.input_tokens is not None:
        print(f"Input token: {result.input_tokens}")
        print(f"Output token: {result.output_tokens}")
        print(f"Toplam token: {result.total_tokens}")
    else:
        print("Token bilgisi alınamadı.")

    if result.latency_ms is not None:
        print(f"Gecikme: {result.latency_ms:.1f} ms")

    if result.estimated_cost_usd is not None:
        print(f"Tahmini maliyet: ${result.estimated_cost_usd:.6f}")
    else:
        print("Tahmini maliyet hesaplanamadı.")

    # Bu duman testi JSON üretmiyor, bu yüzden call_model'in JSON ayrıştırma
    # hatası burada gerçek bir API hatası anlamına gelmez.
    if result.error and result.raw_text is None:
        print(f"Hata: {result.error}")


def main() -> None:
    if not is_api_key_configured():
        print(
            "UYARI: OPENAI_API_KEY tanımlı değil. .env dosyanızı kontrol edin "
            "(.env.example dosyasını referans alabilirsiniz)."
        )
        return

    model_a = os.environ.get("TEXT_MODEL_A", "qwen.qwen3-next-80b-a3b-instruct")
    model_b = os.environ.get("TEXT_MODEL_B", "deepseek.v3.2")

    run_smoke_test(model_a, "Model A")
    run_smoke_test(model_b, "Model B")


if __name__ == "__main__":
    main()
