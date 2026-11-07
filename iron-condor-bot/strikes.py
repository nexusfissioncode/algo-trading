"""Where the four strikes go. Pure: no network, no clock.

Today's options have no delta on Alpaca's free data, so the strikes come from the straddle: the
at-the-money call plus the at-the-money put is what the market charges for today's move, and 85%
of it is the usual yardstick for the expected move. The short strikes sit about that far either
side of the price; each wing is a fixed width further out.

A chain is a list of {"symbol", "strike", "type" ("C" or "P"), "bid", "ask"}."""


def mid(q):
    return round((q["bid"] + q["ask"]) / 2, 4)


def quoted(chain):
    """Only contracts someone is quoting on both sides."""
    return [c for c in chain if c["bid"] > 0 and c["ask"] > 0 and c["ask"] >= c["bid"]]


def straddle(chain, price):
    """The strike nearest the price that has both a call and a put quoted, and what the pair costs."""
    calls = {c["strike"]: c for c in quoted(chain) if c["type"] == "C"}
    puts = {c["strike"]: c for c in quoted(chain) if c["type"] == "P"}
    both = sorted(set(calls) & set(puts), key=lambda k: (abs(k - price), k))
    if not both:
        return None
    k = both[0]
    return {"strike": k, "call": calls[k], "put": puts[k], "cost": round(mid(calls[k]) + mid(puts[k]), 4)}


def _nearest(strikes, target, side):
    """The listed strike at or below (side -1) or at or above (side +1) a target."""
    ok = [k for k in strikes if (k <= target if side < 0 else k >= target)]
    if not ok:
        return None
    return max(ok) if side < 0 else min(ok)


def choose(chain, price, move_factor, wing):
    """The four legs of an iron condor round the price, or None with the reason why not.
    Returns {straddle, move, legs: {short_put, long_put, short_call, long_call}, credit, natural,
    width, max_loss, breakevens}."""
    s = straddle(chain, price)
    if not s:
        return None, "no strike has both a call and a put quoted"
    move = round(s["cost"] * move_factor, 2)
    calls = {c["strike"]: c for c in quoted(chain) if c["type"] == "C"}
    puts = {c["strike"]: c for c in quoted(chain) if c["type"] == "P"}
    sp = _nearest(puts, price - move, -1)
    sc = _nearest(calls, price + move, +1)
    if sp is None or sc is None:
        return None, "no quoted strike as far out as the expected move"
    lp = _nearest(puts, sp - wing, -1)
    lc = _nearest(calls, sc + wing, +1)
    if lp is None or lc is None or lp >= sp or lc <= sc:
        return None, "no quoted wing a whole width out"
    legs = {"short_put": puts[sp], "long_put": puts[lp], "short_call": calls[sc], "long_call": calls[lc]}
    credit = round(mid(legs["short_put"]) + mid(legs["short_call"]) - mid(legs["long_put"]) - mid(legs["long_call"]), 2)
    natural = round(legs["short_put"]["bid"] + legs["short_call"]["bid"] - legs["long_put"]["ask"] - legs["long_call"]["ask"], 2)
    width = max(sp - lp, lc - sc)
    return {"straddle": s, "move": move, "legs": legs, "credit": credit, "natural": natural,
            "width": width, "max_loss": round(width - credit, 2),
            "breakevens": (round(sp - credit, 2), round(sc + credit, 2))}, None
