"""Keep stocks trading above their 200-day average: a dip in a rising stock, not a falling one."""


def describe(settings):
    return f"above their {settings['days']}-day average"


def apply(symbols, market, settings):
    n = settings["days"]
    closes = market.closes(symbols, n)
    return [s for s in symbols if len(closes[s]) >= n and closes[s][-1] > sum(closes[s][-n:]) / n]
