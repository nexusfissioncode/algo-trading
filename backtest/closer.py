"""Getting out: one four-leg order that buys the condor back, at a price that walks.

It starts at the mid. If that does not fill, each step reads the quotes again and asks a little
more, towards the natural price (every short bought at its ask, every wing sold at its bid), then
a few steps past it when the market is running away. An order nobody fills is no exit at all."""
import math

from exits import cost_to_close

OPEN = ("new", "accepted", "pending_new", "partially_filled", "pending_replace", "replaced")


def natural_cost(condor, quotes):
    """Buying back at the worst side of every leg."""
    q = {n: quotes[leg["symbol"]] for n, leg in condor["legs"].items()}
    return round(q["short_put"]["ask"] + q["short_call"]["ask"] - q["long_put"]["bid"] - q["long_call"]["bid"], 2)


def walk(mid, natural, steps, past, tick=0.01):
    """Prices to ask, in order: the mid, then even steps up to the natural price, then `past` more
    steps of the same size beyond it. Never below the mid; whole cents."""
    natural = max(natural, mid)
    size = max(tick, (natural - mid) / steps) if steps else 0
    out = [mid] + [mid + size * k for k in range(1, steps + past + 1)]
    cents = [round(math.ceil(round(p / tick, 6)) * tick, 2) for p in out]
    return [p for i, p in enumerate(cents) if i == 0 or p > cents[i - 1]]


def close(condor, contracts, market, sender, orders, say):
    """Send the buy-back and walk it until it fills. Returns the fill price per share, or None.
    `sender` is the broker (or the replay's pretend broker)."""
    quotes = market.quotes([leg["symbol"] for leg in condor["legs"].values()])
    mid = cost_to_close(condor, quotes)
    if mid is None:
        say("    a leg has no quote right now: the next look tries again")
        return None
    ladder = walk(mid, natural_cost(condor, quotes), orders["walk_steps"], orders["walk_past"])
    price = ladder[0]
    order = sender.close_condor(condor, contracts, price)
    say(f"    buy back the condor at {price:.2f}   -> order {order['status']}")
    for k in range(1, len(ladder)):
        now = sender.wait_order(order["id"], orders["walk_seconds"])
        if now["status"] not in OPEN:
            break
        quotes = market.quotes([leg["symbol"] for leg in condor["legs"].values()])
        fresh = walk(cost_to_close(condor, quotes) or price, natural_cost(condor, quotes), orders["walk_steps"], orders["walk_past"])
        new = max(fresh[min(k, len(fresh) - 1)], price)       # never back the other way
        if new == price:
            continue
        price = new
        order = sender.replace_price(order["id"], price)
        say(f"    not filled in {orders['walk_seconds']}s - asking {price:.2f}   -> order {order['status']}")
    now = sender.wait_order(order["id"], orders["walk_seconds"])
    if now["status"] == "filled":
        fill = abs(float(now["filled_avg_price"]))
        say(f"    filled at {fill:.2f}")
        return fill
    say(f"    still not filled at {price:.2f} ({now['status']}): the next look tries again")
    sender.cancel(order["id"])
    return None
