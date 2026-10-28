"""Keep companies worth at least `min_dollars`: shares from the SEC, times the last price."""


def describe(settings):
    return f"worth over ${settings['min_dollars'] / 1e9:,.0f} billion"


def apply(symbols, market, settings):
    caps = market.market_caps(symbols, settings.get("us_only", True))
    kept = [s for s in symbols if caps.get(s, 0) >= settings["min_dollars"]]
    for s in kept:
        market.note(s, "cap", f"{caps[s] / 1e12:.1f}T" if caps[s] >= 1e12 else f"{caps[s] / 1e9:.0f}bn")
    return kept
