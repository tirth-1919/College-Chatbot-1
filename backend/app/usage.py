"""Provider cost estimates based on operator-configured token rates."""


def estimate_cost_usd(rows, gemini_rate: float, xkiro_rate: float) -> float:
    rates = {"gemini": max(0.0, gemini_rate), "xkiro": max(0.0, xkiro_rate)}
    total = 0.0
    for provider, tokens in rows:
        base_provider = str(provider).split("_", 1)[0].lower()
        if base_provider in rates:
            total += max(0, int(tokens or 0)) * rates[base_provider] / 1_000_000
    return round(total, 6)
