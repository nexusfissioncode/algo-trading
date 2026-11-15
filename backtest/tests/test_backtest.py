"""What the backtest promises: no day left out, the cost sum, windows that never overlap, and a
filter that only looks backwards."""
from datetime import date, datetime, timedelta

from alpaca.data.enums import DataFeed

import backtest as bt
from backtest import Trade


def legs(sp=755, lp=750, sc=765, lc=770):
    return {"credit": 1.0, "legs": {"short_put": {"strike": sp}, "long_put": {"strike": lp},
                                    "short_call": {"strike": sc}, "long_call": {"strike": lc}}}


def trade(day, made, fills=8):
    return Trade(day, "take_profit", made, fills, 1.0)


D = date(2025, 1, 1)


def test_eight_fills_at_a_cent_cost_eight_dollars():
    assert bt.spent(trade(D, 50), 0.01) == 42


def test_a_condor_left_to_expiry_pays_only_the_way_in():
    assert bt.spent(trade(D, 50, fills=4), 0.01) == 46


def test_summary_finds_the_worst_fall():
    st = bt.summary([trade(D, 100), trade(D, -30), trade(D, -50), trade(D, 20)])
    assert st["total"] == 40 and st["fall"] == 80 and st["worst"] == -50 and st["won"] == 50


def test_inside_the_shorts_the_whole_credit_is_kept():
    assert bt.settle(legs(), 760) == 100


def test_past_a_wing_the_most_is_lost():
    assert bt.settle(legs(), 780) == -400 and bt.settle(legs(), 740) == -400


def test_between_short_and_wing_it_is_part_way():
    assert bt.settle(legs(), 767) == -100


def test_break_even_is_where_the_total_reaches_zero():
    t = [trade(D, 80), trade(D, 80)]
    be = bt.break_even(t)
    assert round(bt.summary(t, be)["total"], 6) == 0


def test_no_break_even_when_already_below_zero():
    assert bt.break_even([trade(D, -10)]) is None


def test_a_setting_is_applied_without_touching_the_original():
    base = {"exits": {"stop": 2.0}, "entry": {"wing": 5}}
    s = bt.apply(base, ["exits.stop", "entry.wing"], (3.0, 10))
    assert s == {"exits": {"stop": 3.0}, "entry": {"wing": 10}} and base["exits"]["stop"] == 2.0


def test_the_sweep_file_is_every_combination():
    keys, combos = bt.grid()
    assert len(keys) == 6 and len(combos) == 2400 and len(set(combos)) == 2400


def test_walking_forward_trades_only_after_it_chose():
    days = {date(2024, 2, 1) + timedelta(days=i): None for i in range(1000)}
    rounds = bt.walk_rounds(days)
    assert rounds and all(a < b < c for a, b, c in rounds)
    assert all(rounds[i][2] == rounds[i + 1][1] for i in range(len(rounds) - 1))       # trade windows join up, none overlap


def test_the_winner_is_chosen_on_the_first_period_only():
    cut = date(2025, 1, 1)
    early, late = date(2024, 6, 1), date(2025, 6, 1)
    results = [("a", [trade(early, 100), trade(late, -500)]), ("b", [trade(early, 50), trade(late, 900)])]
    f = bt.sweep_findings(results, cut, 0)
    assert f["best"] == "a" and f["chosen"] == 100 and f["next"] == -500


def test_neighbours_are_one_step_along_one_setting():
    keys = list(bt.grid()[0])
    base = (0.5, 2.0, True, 0.85, 5, "10:00")
    one = (0.4, 2.0, True, 0.85, 5, "10:00")
    two_steps = (0.25, 2.0, True, 0.85, 5, "10:00")
    two_axes = (0.4, 3.0, True, 0.85, 5, "10:00")
    results = [(base, []), (one, [trade(D, 10)]), (two_steps, [trade(D, 20)]), (two_axes, [trade(D, 30)])]
    assert bt.neighbours(results, keys, base, 0) == [10]


def days_with_ranges(ranges):
    """A day per range: the price opens at 100 and reaches 100 + range at the last bar."""
    out = {}
    for i, r in enumerate(ranges):
        d = date(2025, 1, 1) + timedelta(days=i)
        from market import NY
        from datetime import datetime
        t = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY).timestamp()
        out[d] = (([t, t + 22000], [100.0, 100.0 + r]), {})
    return out


def test_a_wide_day_is_judged_only_against_days_before_it():
    ranges = [1.0] * bt.LOOKBACK + [5.0] + [1.0] * 3
    days = days_with_ranges(ranges)
    assert bt.wide_days(days, "close") == {sorted(days)[bt.LOOKBACK]}


def test_a_later_day_cannot_change_what_is_skipped_earlier():
    a = bt.wide_days(days_with_ranges([1.0] * bt.LOOKBACK + [5.0]), "close")
    b = bt.wide_days(days_with_ranges([1.0] * bt.LOOKBACK + [5.0, 900.0]), "close")
    assert a <= b and sorted(a)[0] in b


def test_at_ten_only_finished_bars_count():
    days = days_with_ranges([1.0] * (bt.LOOKBACK + 1))
    assert bt.wide_days(days, "10:00") == set()     # the move comes after 10:00, so nothing looks wide


# --- the feed's holes ------------------------------------------------------------------------------

def bars_by_feed(monkeypatch, counts):
    import broker
    asked = []

    class Stocks:
        def get_stock_bars(self, req):
            asked.append(req.feed)
            return {"SPY": [{"t": i, "c": 1.0} for i in range(counts[req.feed])]}
    monkeypatch.setattr(broker, "stocks", lambda: Stocks())
    return broker, asked


START = datetime(2025, 3, 10, 9, 30)


def test_a_normal_day_stays_on_the_bots_own_feed(monkeypatch):
    broker, asked = bars_by_feed(monkeypatch, {DataFeed.IEX: 204, DataFeed.SIP: 481})
    assert len(broker.stock_minutes("SPY", START, START)) == 204      # a half day is a normal day
    assert asked == [DataFeed.IEX]


def test_a_day_with_a_hole_in_the_free_feed_is_not_lost(monkeypatch, capsys):
    broker, asked = bars_by_feed(monkeypatch, {DataFeed.IEX: 0, DataFeed.SIP: 481})
    assert len(broker.stock_minutes("SPY", START, START)) == 481
    assert asked == [DataFeed.IEX, DataFeed.SIP]
    assert "2025-03-10  0 IEX bars" in capsys.readouterr().out


def test_a_day_with_no_data_at_all_is_named_in_the_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bt, "CACHE", tmp_path)
    assert bt.left_out("SPY") == []
    (tmp_path / "SPY.missing").write_text('["2025-03-10"]')
    assert bt.left_out("SPY") == ["2025-03-10"]
    bt.show_report("SPY", [D, D + timedelta(days=1)], None, [trade(D, 5.0)], 0, None)
    assert "days            2: traded 1, no trade 1, 1 left out, no data" in capsys.readouterr().out


def test_a_walk_forward_round_fits_the_screen(capsys):
    keys = ["exits.take_profit", "exits.stop", "exits.touch", "entry.move_factor", "entry.wing", "entry.at"]
    rows = [dict(start=D, end=D, chosen=3140.0, next=-1837.0, values=(0.75, 99.0, False, 1.4, 10, "11:00"))]
    bt.show_walk(keys, rows, 0)
    assert max(len(line) for line in capsys.readouterr().out.splitlines()) <= 100


def test_the_report_says_what_the_free_data_cannot_test(capsys):
    bt.show_report("SPY", [D], None, [trade(D, 5.0)], 0, None)
    assert "not tested      fills at the real spread (not in Alpaca's free data)" in capsys.readouterr().out


def test_a_fetch_can_stop_on_a_given_day(monkeypatch):
    import broker
    asked = []

    class Trading:
        def get_calendar(self, req):
            asked.append(req.end)
            return [{"date": "2026-10-30"}]
    monkeypatch.setattr(broker, "trading", lambda: Trading())
    assert bt.trading_days(until="2026-10-30") == [date(2026, 10, 30)]
    assert asked == [date(2026, 10, 30)]
