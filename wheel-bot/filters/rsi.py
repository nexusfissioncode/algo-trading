"""Keep stocks whose RSI on daily closes is under `below` - "oversold"."""


def rsi(closes, n=14):
    """Wilder's RSI: the average gain against the average loss over n days, on a scale of 0 to 100."""
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(c, 0) for c in changes[:n]) / n
    loss = sum(max(-c, 0) for c in changes[:n]) / n
    for c in changes[n:]:
        gain = (gain * (n - 1) + max(c, 0)) / n
        loss = (loss * (n - 1) + max(-c, 0)) / n
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def describe(settings):
    return f"RSI({settings['days']}) under {settings['below']}"


def apply(symbols, market, settings):
    n = settings["days"]
    closes = market.closes(symbols, n * 5)        # a longer run of days settles Wilder's average
    kept = []
    for s in symbols:
        if len(closes[s]) > n + 1:
            value = rsi(closes[s], n)
            if value < settings["below"]:
                market.note(s, "RSI", f"{value:.1f}")
                kept.append(s)
    return kept
