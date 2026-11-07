"""The market the bot sees: today's, live, or a past day's, replayed minute by minute.

Both answer the same questions - what time is it, where is the price, what does today's chain
look like, what are these options quoted at - so the rest of the code cannot tell which it has.
A replay also pretends to be the broker: it fills every order at the price asked, which is an
estimate (one-minute bars are trades, not quotes)."""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from broker import kind, strike

NY = ZoneInfo("America/New_York")
CACHE = Path(__file__).parent / ".cache"
BAND = 0.05                     # strikes within 5% of the price are fetched


def occ(stock, expiry, kind, strike):
    """An option's symbol: SPY, 26 Oct 2026, put, 755 -> SPY261026P00755000."""
    return f"{stock}{expiry:%y%m%d}{kind}{round(strike * 1000):08d}"


class Live:
    replay = False

    def __init__(self, stock, broker):
        self.stock, self.broker = stock, broker

    def now(self):
        return datetime.now(NY)

    def today(self):
        return self.now().date()

    def price(self):
        return self.broker.price(self.stock)

    def chain(self):
        p = self.price()
        return self.broker.chain(self.stock, self.today(), round(p * (1 - BAND)), round(p * (1 + BAND)))

    def quotes(self, symbols):
        return self.broker.quotes(symbols)

    def sleep(self, seconds):
        time.sleep(seconds)

    def sleep_until(self, hhmm):
        h, m = map(int, hhmm.split(":"))
        target = self.now().replace(hour=h, minute=m, second=0, microsecond=0)
        while self.now() < target:
            time.sleep(min(30, (target - self.now()).total_seconds()))


class Replay:
    """A past trading day, from one-minute bars. The clock starts at 9:30 New York and only moves
    when the bot sleeps; the price and each option are their last trade at or before the clock."""
    replay = True

    def __init__(self, stock, day, broker=None, bars=None):
        self.stock, self.day = stock, day
        if bars is None:
            bars = self._load(broker)
        self.spy = [(datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY), b["c"]) for b in bars["stock"]]
        self.opts = {s: [(datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY), b["c"]) for b in rows]
                     for s, rows in bars["options"].items()}
        self.clock = datetime(day.year, day.month, day.day, 9, 30, tzinfo=NY)
        self.orders, self.next_id = {}, 1

    def _load(self, broker):
        """Fetched once per day and kept in .cache/, so a replay runs again without the network."""
        CACHE.mkdir(exist_ok=True)
        f = CACHE / f"{self.stock}-{self.day.isoformat()}.json"
        if f.exists():
            return json.loads(f.read_text())
        start = datetime(self.day.year, self.day.month, self.day.day, 9, 30, tzinfo=NY)
        end = start.replace(hour=16, minute=15)
        stock = broker.stock_minutes(self.stock, start, end)
        if not stock:
            raise SystemExit(f"no bars for {self.stock} on {self.day} - was the market open?")
        first = stock[0]["c"]
        strikes = range(int(first * (1 - BAND)), int(first * (1 + BAND)) + 1)
        symbols = [occ(self.stock, self.day, k, s) for s in strikes for k in "CP"]
        data = {"stock": stock, "options": broker.option_minutes(symbols, start, end)}
        f.write_text(json.dumps(data))
        return data

    @staticmethod
    def _at(rows, t):
        last = None
        for when, c in rows:
            if when > t:
                break
            last = c
        return last

    def now(self):
        return self.clock

    def today(self):
        return self.day

    def price(self):
        return self._at(self.spy, self.clock)

    def quotes(self, symbols):
        out = {}
        for s in symbols:
            c = self._at(self.opts.get(s, []), self.clock)
            if c is not None:
                out[s] = {"bid": c, "ask": c}
        return out

    def chain(self):
        return [{"symbol": s, "strike": strike(s), "type": kind(s), **q} for s, q in self.quotes(self.opts).items()]

    def sleep(self, seconds):
        self.clock += timedelta(seconds=seconds)

    def sleep_until(self, hhmm):
        h, m = map(int, hhmm.split(":"))
        self.clock = max(self.clock, self.clock.replace(hour=h, minute=m, second=0))

    def finished(self):
        return self.clock.time() >= datetime(2000, 1, 1, 16, 0).time()

    # --- the pretend broker: every order fills at its price ---

    def _fill(self, price):
        oid = str(self.next_id)
        self.next_id += 1
        self.orders[oid] = {"id": oid, "status": "filled", "filled_avg_price": price}
        return self.orders[oid]

    def open_condor(self, condor, qty, credit):
        return self._fill(-credit)

    def close_condor(self, condor, qty, cost):
        return self._fill(cost)

    def wait_order(self, order_id, seconds=0):
        return self.orders[order_id]

    def replace_price(self, order_id, price):
        return self._fill(price)

    def replace_credit(self, order_id, credit):
        return self._fill(-credit)

    def cancel(self, order_id):
        pass

    def positions(self):
        return []
