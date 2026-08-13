from services.comparison import ModelMetrics, build_comparison_summary, pick_lowest


def test_pick_lowest_basic():
    winners = pick_lowest([("A", 2.0), ("B", 1.0)])
    assert winners == ["B"]


def test_pick_lowest_handles_none_values():
    winners = pick_lowest([("A", None), ("B", 1.0)])
    assert winners == ["B"]


def test_pick_lowest_all_none_returns_none():
    assert pick_lowest([("A", None), ("B", None)]) is None


def test_pick_lowest_tie_returns_both():
    winners = pick_lowest([("A", 1.0), ("B", 1.0)])
    assert set(winners) == {"A", "B"}


def test_comparison_summary_selects_cheapest_and_fastest():
    models = [
        ModelMetrics(label="Plan A", cost=0.001, latency_ms=500, total_tokens=100, json_valid=True, schema_valid=True),
        ModelMetrics(label="Plan B", cost=0.002, latency_ms=800, total_tokens=150, json_valid=True, schema_valid=True),
    ]
    lines = build_comparison_summary(models)
    assert any("Bu çalıştırmada maliyet lideri: Plan A" in line for line in lines)
    assert any("En hızlı model: Plan A" in line for line in lines)
    assert any("En düşük token kullanımı: Plan A" in line for line in lines)
    assert any("Her iki model de JSON ve şema doğrulamasını geçti." == line for line in lines)


def test_comparison_summary_handles_none_without_crashing():
    models = [
        ModelMetrics(label="Plan A", cost=None, latency_ms=None, total_tokens=None, json_valid=False, schema_valid=False),
        ModelMetrics(label="Plan B", cost=0.002, latency_ms=800, total_tokens=150, json_valid=True, schema_valid=True),
    ]
    lines = build_comparison_summary(models)
    assert any("Bu çalıştırmada maliyet lideri: Plan B" in line for line in lines)
    assert any("Plan A: JSON ayrıştırma başarısız" in line for line in lines)
    assert any("Plan B: JSON ayrıştırma geçti" in line for line in lines)


def test_comparison_summary_no_measurements_reports_not_measured():
    models = [
        ModelMetrics(label="Plan A", cost=None, latency_ms=None, total_tokens=None, json_valid=True, schema_valid=True),
        ModelMetrics(label="Plan B", cost=None, latency_ms=None, total_tokens=None, json_valid=True, schema_valid=True),
    ]
    lines = build_comparison_summary(models)
    assert "Maliyet karşılaştırması: Hiçbir model için ölçülemedi." in lines
    assert "Gecikme karşılaştırması: Hiçbir model için ölçülemedi." in lines
    assert "Token kullanımı karşılaştırması: Hiçbir model için ölçülemedi." in lines
