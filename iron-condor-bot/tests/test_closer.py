"""The closing walk: from the mid towards the natural price and past it, never backwards."""
import closer
from helpers import Market, Sender, condor, quotes_for

ORDERS = {"walk_steps": 4, "walk_past": 2, "walk_seconds": 0}


def test_the_walk_starts_at_the_mid_and_climbs_in_even_steps():
    assert closer.walk(1.00, 1.40, 4, 2) == [1.00, 1.10, 1.20, 1.30, 1.40, 1.50, 1.60]


def test_the_walk_moves_at_least_a_cent_a_step():
    assert closer.walk(0.05, 0.05, 2, 1) == [0.05, 0.06, 0.07, 0.08]


def test_the_natural_price_buys_the_shorts_at_the_ask_and_sells_the_wings_at_the_bid():
    c = condor()
    q = quotes_for(c, 0.9, 0.2, 0.8, 0.1, spread=0.05)
    assert closer.natural_cost(c, q) == 1.6


def test_close_fills_at_the_mid_when_someone_takes_it():
    c = condor()
    s = Sender(fills_at=1.4)
    fill = closer.close(c, 1, Market(quotes_for(c, 0.9, 0.2, 0.8, 0.1, spread=0.05)), s, ORDERS, lambda *_: None)
    assert fill == 1.4 and s.asked == [1.4]


def test_close_walks_until_it_fills():
    c = condor()
    s = Sender(fills_at=1.5)
    fill = closer.close(c, 1, Market(quotes_for(c, 0.9, 0.2, 0.8, 0.1, spread=0.05)), s, ORDERS, lambda *_: None)
    assert s.asked == [1.4, 1.45, 1.5]
    assert fill == 1.5


def test_close_gives_up_and_cancels_when_nobody_fills():
    c = condor()
    s = Sender(fills_at=None)
    said = []
    fill = closer.close(c, 1, Market(quotes_for(c, 0.9, 0.2, 0.8, 0.1, spread=0.05)), s, ORDERS, said.append)
    assert fill is None and s.cancelled
    assert s.asked == sorted(s.asked) and s.asked[-1] > 1.6        # went past the natural price
    assert "next look" in said[-1]


def test_close_waits_for_a_quote_on_every_leg():
    c = condor()
    q = quotes_for(c, 0.9, 0.2, 0.8, 0.1)
    q.pop(c["legs"]["short_put"]["symbol"])
    s = Sender(fills_at=0)
    assert closer.close(c, 1, Market(q), s, ORDERS, lambda *_: None) is None
    assert s.asked == []
