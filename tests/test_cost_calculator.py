from services.cost_calculator import estimate_cost_usd

PRICES = {
    "test-model": {
        "display_name": "Test Model",
        "input_per_million": 1.0,
        "output_per_million": 2.0,
    }
}


def test_estimate_cost_basic():
    cost = estimate_cost_usd("test-model", 1_000_000, 1_000_000, prices=PRICES)
    assert cost == 3.0


def test_estimate_cost_partial_tokens():
    cost = estimate_cost_usd("test-model", 500_000, 250_000, prices=PRICES)
    assert cost == 1.0


def test_estimate_cost_missing_tokens_returns_none():
    assert estimate_cost_usd("test-model", None, 100, prices=PRICES) is None
    assert estimate_cost_usd("test-model", 100, None, prices=PRICES) is None


def test_estimate_cost_unknown_model_returns_none():
    assert estimate_cost_usd("unknown-model", 100, 100, prices=PRICES) is None
