"""Small builders shared by the tests: a chain, a condor, a pretend broker."""
from datetime import date

DAY = date(2026, 10, 26)


def sym(kind, strike):
    return f"SPY{DAY:%y%m%d}{kind}{round(strike * 1000):08d}"


def leg(kind, strike, bid, ask):
    return {"symbol": sym(kind, strike), "strike": strike, "type": kind, "bid": bid, "ask": ask}


def chain(price=760, half=10):
    """A tidy chain round `price`: out of the money, each strike is worth 70% of the last."""
    out = []
    for k in range(price - half, price + half + 1):
        c = round(3.0 * 0.7 ** (k - price), 2) if k >= price else round(3.0 + (price - k), 2)
        p = round(3.0 * 0.7 ** (price - k), 2) if k <= price else round(3.0 + (k - price), 2)
        for kind, v in (("C", c), ("P", p)):
            v = max(v, 0.02)
            out.append(leg(kind, k, round(v * 0.97, 2), round(v * 1.03, 2)))
    return out


def condor(credit=1.00, sp=755, sc=765, wing=5):
    return {"credit": credit,
            "legs": {"short_put": leg("P", sp, 0, 0), "long_put": leg("P", sp - wing, 0, 0),
                     "short_call": leg("C", sc, 0, 0), "long_call": leg("C", sc + wing, 0, 0)}}


def quotes_for(c, sp, lp, sc, lc, spread=0.0):
    """Quotes whose mids are the four given prices."""
    m = {"short_put": sp, "long_put": lp, "short_call": sc, "long_call": lc}
    return {c["legs"][n]["symbol"]: {"bid": round(v - spread, 2), "ask": round(v + spread, 2)} for n, v in m.items()}


class Sender:
    """A pretend broker: an order fills once its price reaches `fills_at` (a buy-back at or above,
    an entry credit at or below). Records every price asked."""

    def __init__(self, fills_at=None, credit_fills_at=None):
        self.fills_at, self.credit_fills_at = fills_at, credit_fills_at
        self.asked, self.cancelled, self.orders, self.n = [], [], {}, 0

    def _order(self, price, kind):
        self.n += 1
        oid = str(self.n)
        self.asked.append(price)
        if kind == "close":
            ok = self.fills_at is not None and price >= self.fills_at
        else:
            ok = self.credit_fills_at is not None and -price <= self.credit_fills_at
        self.orders[oid] = {"id": oid, "status": "filled" if ok else "new", "filled_avg_price": price, "kind": kind}
        return self.orders[oid]

    def close_condor(self, condor, qty, cost):
        return self._order(cost, "close")

    def open_condor(self, condor, qty, credit):
        return self._order(-credit, "open")

    def replace_price(self, oid, price):
        return self._order(price, "close")

    def replace_credit(self, oid, credit):
        return self._order(-credit, "open")

    def wait_order(self, oid, seconds=0):
        return self.orders[oid]

    def cancel(self, oid):
        self.cancelled.append(oid)


class Market:
    """Fixed quotes, a clock that moves when slept."""
    replay = False

    def __init__(self, quotes, price=760, now=None):
        self._quotes, self._price, self.clock = quotes, price, now

    def quotes(self, symbols):
        return {s: self._quotes[s] for s in symbols if s in self._quotes}

    def price(self):
        return self._price

    def now(self):
        return self.clock

    def today(self):
        return DAY

    def sleep(self, seconds):
        pass
