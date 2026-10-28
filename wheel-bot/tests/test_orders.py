"""Walking an order's price toward the bid while it does not fill, with Alpaca stood in for."""
import rank
import wheel


def quote(bid, ask, penny=True):
    return {"bid": bid, "ask": ask, "penny": penny}


def test_a_walk_goes_from_the_mid_to_the_bid_in_steps():
    # AMAT's 355 put on 22 Oct: 13.90 x 15.40, five-cent steps
    prices = rank.walk(quote(13.90, 15.40), "sell", "mid", 4)
    assert prices[0] == 14.65 and prices[-1] == 13.90
    assert all(a > b for a, b in zip(prices, prices[1:]))            # always lower, never back up
    assert all(abs(p * 20 - round(p * 20)) < 1e-6 for p in prices)  # each on a five-cent step


def test_a_buy_walks_up_to_the_ask():
    prices = rank.walk(quote(0.50, 0.60), "buy", "mid", 4)
    assert prices[0] == 0.55 and prices[-1] == 0.60 and prices == sorted(prices)


def test_no_walk_when_off_or_already_at_the_bid():
    assert rank.walk(quote(13.90, 15.40), "sell", "mid", 0) == [14.65]
    assert rank.walk(quote(13.90, 15.40), "sell", "natural", 4) == [13.90]
    assert rank.walk(quote(0.64, 0.65), "sell", "mid", 4) == [0.64]          # a one-cent market


class FakeBroker:
    """Fills an order once its price is at or under `fills_at`."""
    def __init__(self, fills_at):
        self.fills_at, self.asked, self.n = fills_at, [], 0

    def send(self, option, qty, price):
        return self._order(price)

    def _order(self, price):
        self.n += 1
        self.asked.append(price)
        return {"id": str(self.n), "status": "new", "price": price}

    def wait_order(self, order_id, seconds):
        price = self.asked[int(order_id) - 1]
        if price <= self.fills_at:
            return {"id": order_id, "status": "filled", "filled_avg_price": str(price)}
        return {"id": order_id, "status": "new"}

    def replace_price(self, order_id, price):
        return self._order(price)


def run_place(monkeypatch, fills_at, trade=True, quotes=None, past=0):
    fake, said = FakeBroker(fills_at), []
    later = iter(quotes or [])
    monkeypatch.setattr(wheel.broker, "option_quote", lambda option: next(later, {"bid": 13.90, "ask": 15.40}))
    monkeypatch.setattr(wheel.broker, "wait_order", fake.wait_order)
    monkeypatch.setattr(wheel.broker, "replace_price", fake.replace_price)
    monkeypatch.setattr(wheel, "say", lambda line="": said.append(line))
    order = wheel.place(trade, "sell to open", "AMAT261127P00355000", 1, quote(13.90, 15.40), "sell", fake.send,
                        {"price": "mid", "walk_steps": 4, "walk_seconds": 0, "walk_past": past})
    return fake, said, order


def test_place_stops_walking_once_filled(monkeypatch):
    fake, said, order = run_place(monkeypatch, fills_at=14.30)
    assert fake.asked[0] == 14.65 and fake.asked[-1] <= 14.30 and 13.90 not in fake.asked
    assert order["status"] == "filled" and said[-1].startswith("    filled at ")


def test_place_leaves_it_up_when_even_the_bid_does_not_fill(monkeypatch):
    fake, said, order = run_place(monkeypatch, fills_at=10)
    assert fake.asked[-1] == 13.90 and order["status"] == "new"
    assert "stays up for the day" in said[-1]


def test_a_dry_run_sends_nothing(monkeypatch):
    fake, said, order = run_place(monkeypatch, fills_at=99, trade=False)
    assert order is None and fake.asked == [] and said == ["    sell to open 1 AMAT261127P00355000 at 14.65   (dry run)"]


def test_the_walk_follows_a_falling_bid(monkeypatch):
    # AMAT on 22 Oct: the bid fell from 13.90 to 13.01 while the order waited
    falling = [{"bid": b, "ask": b + 1.5} for b in (13.60, 13.30, 13.01, 13.01)]
    fake, said, order = run_place(monkeypatch, fills_at=13.01, quotes=falling)
    assert fake.asked[-1] == 13.01 and order["status"] == "filled"
    assert fake.asked == sorted(fake.asked, reverse=True)


def test_a_rising_bid_never_walks_the_price_back_up(monkeypatch):
    rising = [{"bid": b, "ask": b + 1.5} for b in (14.5, 15.0, 15.5, 16.0)]
    fake, said, order = run_place(monkeypatch, fills_at=0, quotes=rising)
    assert max(fake.asked) == fake.asked[0] == 14.65


def test_walk_past_goes_a_few_steps_beyond_the_bid():
    assert rank.walk(quote(13.39, 15.00), "sell", "mid", 4, past=2)[-3:] == [13.39, 13.34, 13.29]
    assert rank.walk(quote(0.50, 0.60), "buy", "mid", 4, past=2)[-2:] == [0.61, 0.62]
    assert rank.walk(quote(0.01, 0.03), "sell", "natural", 4, past=3)[-1] == 0.01      # never under a cent


def test_place_fills_past_the_bid_the_free_quote_shows(monkeypatch):
    # 22 Oct: the order sat at the bid the bot could see, 13.39, and the broker filled lower
    fake, said, order = run_place(monkeypatch, fills_at=13.30, quotes=[{"bid": 13.39, "ask": 15.0}] * 8, past=2)
    assert order["status"] == "filled" and fake.asked[-1] == 13.29
