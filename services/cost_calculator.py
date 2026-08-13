"""Bedrock model çağrıları için tahmini maliyet hesaplama."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

PRICES_PATH = Path(__file__).resolve().parent.parent / "config" / "model_prices.json"


def load_model_prices(path: Path = PRICES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_display_name(model_id: str, prices: Optional[dict] = None) -> str:
    prices = prices if prices is not None else load_model_prices()
    entry = prices.get(model_id)
    if entry:
        return entry.get("display_name", model_id)
    return model_id


def estimate_cost_usd(
    model_id: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    prices: Optional[dict] = None,
) -> Optional[float]:
    """Verilen token sayılarına göre tahmini maliyeti USD olarak hesaplar.

    Token bilgisi yoksa None döner; maliyet uydurulmaz.
    """
    if input_tokens is None or output_tokens is None:
        return None

    prices = prices if prices is not None else load_model_prices()
    entry = prices.get(model_id)
    if entry is None:
        return None

    input_price = entry["input_per_million"]
    output_price = entry["output_per_million"]

    cost = (input_tokens / 1_000_000 * input_price) + (
        output_tokens / 1_000_000 * output_price
    )
    return round(cost, 6)
