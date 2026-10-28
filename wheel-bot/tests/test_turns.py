"""Every turn of the wheel, on made-up positions - nothing here talks to Alpaca.

  uv run pytest -v tests/test_turns.py"""
import tomllib
from datetime import date
from pathlib import Path

import decide

SETTINGS = tomllib.loads((Path(__file__).parent.parent / "wheel.toml").read_text())
TODAY = date(2026, 10, 21)


def option(symbol, qty, entry, now):
    return {"symbol": symbol, "qty": str(qty), "avg_entry_price": str(entry), "current_price": str(now)}


def shares(symbol, qty, cost):
    return {"symbol": symbol, "qty": str(qty), "avg_entry_price": str(cost), "current_price": str(cost)}


def actions(positions, orders=()):
    return [(a.symbol, a.do) for a in decide.decide(positions, list(orders), SETTINGS, TODAY)]


# --- where each stock is on the wheel ------------------------------------------------------------

def test_reads_an_option_symbol():
    assert decide.parse_option("BAC261120P00049000") == ("BAC", date(2026, 11, 20), "put", 49.0)
    assert decide.parse_option("BRK.B261218C00500000")[2:] == ("call", 500.0)
    assert decide.parse_option("BAC") is None


def test_a_fresh_put_is_left_to_run():
    assert actions([option("BAC261127P00049000", -1, 0.65, 0.60)]) == [("BAC", "hold")]


def test_a_put_at_half_profit_is_bought_back():
    assert actions([option("BAC261127P00049000", -1, 0.66, 0.33)]) == [("BAC", "buy back")]


def test_a_put_near_expiry_is_rolled():
    assert actions([option("BAC261106P00049000", -1, 0.65, 0.50)]) == [("BAC", "roll")]   # 16 days


def test_a_put_on_its_last_day_waits_for_the_close():
    assert actions([option("BAC261021P00049000", -1, 0.65, 0.05)]) == [("BAC", "hold")]


def test_an_expired_put_means_the_stock_is_free_again():
    # Alpaca removes an expired option; with nothing held, the stock may get a new put.
    room, in_wheel = decide.room_for_puts([], [], SETTINGS)
    assert room == 1 and "BAC" not in in_wheel


def test_assigned_shares_get_a_covered_call():
    [a] = decide.decide([shares("BAC", 100, 49.0)], [], SETTINGS, TODAY)
    assert (a.do, a.qty, a.cost) == ("sell call", 1, 49.0)


def test_two_hundred_shares_get_two_calls():
    [a] = decide.decide([shares("BAC", 200, 49.0)], [], SETTINGS, TODAY)
    assert (a.do, a.qty) == ("sell call", 2)


def test_covered_shares_are_not_sold_another_call():
    assert actions([shares("BAC", 100, 49.0), option("BAC261127C00052000", -1, 0.80, 0.70)]) == \
        [("BAC", "hold")]


def test_fewer_than_a_hundred_shares_just_hold():
    assert actions([shares("BAC", 40, 49.0)]) == [("BAC", "hold")]


def test_called_away_means_back_to_puts():
    # The shares are gone and so is the call: nothing held, the stock may get a put again.
    assert actions([]) == []
    assert decide.room_for_puts([], [], SETTINGS)[0] == 1


def test_an_open_order_means_wait():
    assert actions([shares("BAC", 100, 49.0)], [{"symbol": "BAC261127C00052000"}]) == [("BAC", "wait")]


def test_a_put_sent_but_not_filled_shows_as_waiting():
    # Nothing held yet, only the order: it is in the wheel, and no second put goes on top of it.
    assert actions([], [{"symbol": "AMAT261127P00355000"}]) == [("AMAT", "wait")]
    assert "AMAT" in decide.room_for_puts([], [{"symbol": "AMAT261127P00355000"}], SETTINGS)[1]


def test_no_new_put_when_the_wheel_is_full():
    held = [option(f"{s}261127P00049000", -1, 1, 1) for s in ("BAC", "WMT", "KO")]
    assert decide.room_for_puts(held, [], SETTINGS)[0] == 0
