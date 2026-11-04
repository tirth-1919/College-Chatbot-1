from app.usage import estimate_cost_usd


def test_estimate_cost_uses_configured_rates_for_provider_variants():
    rows = [("gemini_translation", 500_000), ("xkiro", 250_000), ("unknown", 900_000)]
    assert estimate_cost_usd(rows, gemini_rate=2.0, xkiro_rate=4.0) == 2.0


def test_estimate_cost_is_zero_when_rates_are_unconfigured():
    assert estimate_cost_usd([("gemini_embedding", 1_000_000)], 0, 0) == 0
