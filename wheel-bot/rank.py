"""Choosing an option, and ranking stocks by what their put pays. Pure, tested in tests/test_rank.py.

A contract here is a dict: symbol, strike, expiry (a date), delta, bid, ask, open_interest, penny
(True when it trades in one-cent steps under three dollars)."""
import math


def mid(c):
    return (c["bid"] + c["ask"]) / 2


def tick(price, penny):
    """The price step an option trades in: penny names in cents under $3, everything else coarser."""
    if penny:
        return 0.01 if price < 3 else 0.05
    return 0.05 if price < 3 else 0.10


def limit_price(c, side, how="mid"):
    """A sell rounds down to the step, a buy rounds up, so the order is never worse than the mid.
    "natural" sells at the bid and buys at the ask."""
    if how == "natural":
        return round(c["bid"] if side == "sell" else c["ask"], 2)
    step = tick(mid(c), c.get("penny", True))
    n = mid(c) / step
    n = math.floor(n + 1e-9) if side == "sell" else math.ceil(n - 1e-9)
    return round(max(n, 1) * step, 2)


def walk(c, side, how="mid", steps=0, past=0):
    """The prices an order asks, in turn, while it waits to fill: from limit_price to the bid (a
    sell) or the ask (a buy) in `steps` moves, each on the price step, then `past` steps beyond it -
    the free quotes are not quite the market the broker fills against. [one price] when steps is 0."""
    first, last = limit_price(c, side, how), limit_price(c, side, "natural")
    if steps <= 0:
        return [first]
    step = tick(mid(c), c.get("penny", True))
    prices = [first]
    for k in range(1, steps):
        p = round(round((first + (last - first) * k / steps) / step) * step, 2)
        if p != prices[-1] and (p - last) * (first - last) > 0:      # still short of the bid or ask
            prices.append(p)
    if last != prices[-1]:
        prices.append(last)
    sign = -1 if side == "sell" else 1
    return prices + [round(max(last + sign * step * j, 0.01), 2) for j in range(1, past + 1)]


def why_not(c, today, rules):
    """None if the contract may be traded, or the reason it may not."""
    days = (c["expiry"] - today).days
    if not rules["min_days"] <= days <= rules["max_days"]:
        return "outside the days window"
    if c.get("delta") is None:
        return "no delta in the data"
    if abs(abs(c["delta"]) - rules["delta"]) > rules["delta_within"]:
        return "delta too far from the target"
    if c["bid"] <= 0:
        return "nobody is bidding"
    if c.get("open_interest", 0) < rules["min_open_interest"]:
        return "too little open interest"
    if (c["ask"] - c["bid"]) / mid(c) > rules["max_spread"]:
        return "bid and ask too far apart"
    return None


def choose(contracts, today, rules, strike_min=None, strike_max=None):
    """(the contract whose delta is nearest the target, None) - or (None, why there is none)."""
    if not contracts:
        return None, f"no contracts {rules['min_days']}-{rules['max_days']} days out"
    ok = [c for c in contracts if why_not(c, today, rules) is None]
    if not ok:
        reasons = {why_not(c, today, rules) for c in contracts}
        return None, reasons.pop() if len(reasons) == 1 else "none near the target delta trades well"
    fits = [c for c in ok if (strike_min is None or c["strike"] >= strike_min)
            and (strike_max is None or c["strike"] <= strike_max)]
    if not fits:
        near = min(ok, key=lambda c: abs(abs(c["delta"]) - rules["delta"]))
        if strike_max is not None and near["strike"] > strike_max:
            return None, f"strike {near['strike']:g} is nearest the target and sets aside " \
                         f"${near['strike'] * 100:,.0f}, more than allowed"
        return None, f"nothing near the target at or above {strike_min:.2f}"
    return min(fits, key=lambda c: (abs(abs(c["delta"]) - rules["delta"]), -mid(c))), None


def score(c, today):
    """What a put pays for the cash it ties up: premium over strike, and that over a year."""
    days = (c["expiry"] - today).days
    back = mid(c) / c["strike"]
    return {"premium": round(mid(c) * 100, 2), "cash": round(c["strike"] * 100, 2),
            "return": back, "yearly": back * 365 / days, "days": days}


def rank(chosen, today):
    """[(stock, contract)] -> the same, best paying first (for a year, since expiries differ)."""
    scored = [(stock, c, score(c, today)) for stock, c in chosen if c is not None]
    return sorted(scored, key=lambda x: -x[2]["yearly"])
