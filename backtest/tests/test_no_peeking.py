"""A replay may only see what was known at that moment: a bar's close arrives when the bar ends."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from market import Replay

NY = ZoneInfo("America/New_York")
DAY = date(2026, 10, 26)


def stamp(hour, minute):
    return datetime(2026, 10, 26, hour, minute, tzinfo=NY).isoformat()


def replay():
    bars = [{"t": stamp(9, 59), "c": 100.0}, {"t": stamp(10, 0), "c": 200.0}, {"t": stamp(10, 1), "c": 300.0}]
    return Replay("SPY", DAY, bars={"stock": bars, "options": {}})


def at(r, hour, minute):
    r.clock = datetime(2026, 10, 26, hour, minute, tzinfo=NY)
    return r.price()


def test_at_ten_the_ten_oclock_bar_has_not_finished():
    assert at(replay(), 10, 0) == 100.0


def test_a_bar_is_known_once_it_has_finished():
    assert at(replay(), 10, 1) == 200.0


def test_before_any_bar_has_finished_there_is_no_price():
    assert at(replay(), 9, 59) is None
