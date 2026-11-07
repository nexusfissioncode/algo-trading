"""A whole day: entering, giving up, a restart that finds the open condor, closing by hand, and
a replayed day on made-up bars."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import condor
from helpers import DAY, Market, Sender, chain, quotes_for, sym
from market import Replay, occ

NY = ZoneInfo("America/New_York")
S = condor.settings()
ENTRY = S["entry"]


def quiet(*_):
    pass


def pick():
    from strikes import choose
    return choose(chain(760, half=15), 760, 0.85, 5)[0]


def test_settings_can_be_changed_for_one_run():
    s = condor.settings(changes=["exits.stop=3", "exits.close_by=15:00", "exits.touch=false"])
    assert s["exits"]["stop"] == 3 and s["exits"]["close_by"] == "15:00" and s["exits"]["touch"] is False


def test_entry_fills_at_the_mid():
    s = Sender(credit_fills_at=pick()["credit"])
    assert condor.enter(pick(), 1, ENTRY, s, quiet) == pick()["credit"]


def test_entry_asks_once_more_then_gives_up():
    p = pick()
    s = Sender(credit_fills_at=0.0)
    said = []
    assert condor.enter(p, 1, ENTRY, s, said.append) is None
    assert len(s.asked) == 2 and -s.asked[1] < p["credit"] and s.cancelled
    assert "No condor today" in said[-1]


def test_entry_never_asks_less_than_the_least_credit():
    p = {**pick(), "credit": 0.40, "natural": 0.10}
    s = Sender(credit_fills_at=0.0)
    condor.enter(p, 1, {**ENTRY, "least_credit": 0.30}, s, quiet)
    assert -s.asked[1] == 0.30


def position(kind, strike, qty, price, day=DAY):
    return {"symbol": occ("SPY", day, kind, strike), "qty": str(qty), "avg_entry_price": str(price)}


HELD = [position("P", 750, 1, 0.20), position("P", 755, -1, 0.70),
        position("C", 765, -1, 0.60), position("C", 770, 1, 0.10)]


def test_a_restart_rebuilds_the_condor_from_the_account():
    c = condor.from_positions(HELD + [{"symbol": "AAPL", "qty": "10", "avg_entry_price": "200"}], "SPY", DAY)
    assert c["credit"] == 1.0 and c["contracts"] == 1
    assert c["legs"]["short_put"]["strike"] == 755 and c["legs"]["long_call"]["strike"] == 770


def test_yesterdays_legs_are_not_todays_condor():
    old = [position(k, s, q, p, day=DAY - timedelta(days=3)) for k, s, q, p in
           (("P", 750, 1, .2), ("P", 755, -1, .7), ("C", 765, -1, .6), ("C", 770, 1, .1))]
    assert condor.from_positions(old, "SPY", DAY) is None


def test_close_now_closes_the_condor_found_in_the_account():
    c = condor.from_positions(HELD, "SPY", DAY)
    q = quotes_for(c, 0.5, 0.1, 0.4, 0.05)
    m = Market(q, now=datetime(2026, 10, 26, 11, 0, tzinfo=NY))
    s = Sender(fills_at=0)
    said = []
    rule, made = condor.run(m, s, S, close_now=True, positions=lambda: HELD, say=said.append)
    assert rule == "by hand" and made == round((1.0 - 0.75) * 100, 2)
    assert any("found an open condor" in l for l in said)
    assert said[0].endswith("trading, paper account")      # it sends orders, so it never says "dry run"


def test_a_dry_run_sends_nothing():
    m = Market({}, now=datetime(2026, 10, 26, 10, 30, tzinfo=NY))
    m.chain = lambda: chain(760, half=15)
    s = Sender()
    said = []
    got = condor.run(m, s, S, say=said.append)
    assert got["legs"] and s.asked == [] and "dry run" in said[-1]


def test_too_late_to_open_after_the_closing_time():
    m = Market({}, now=datetime(2026, 10, 26, 15, 20, tzinfo=NY))
    said = []
    assert condor.run(m, Sender(), S, trade=True, say=said.append) is None
    assert "too late" in said[-1]


def bars_for_a_quiet_day(day):
    """SPY sits at 760 all day; every option loses value steadily from 10:00 to 16:00."""
    start = datetime(day.year, day.month, day.day, 9, 30, tzinfo=NY)
    minutes = [start + timedelta(minutes=i) for i in range(391)]
    stamp = lambda t: t.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    stock = [{"t": stamp(t), "c": 760.0} for t in minutes]
    options = {}
    for leg in chain(760, half=15):
        rows = []
        for i, t in enumerate(minutes):
            left = max(0.0, 1 - max(0, i - 30) / 360)          # full value until 10:00, then decays
            rows.append({"t": stamp(t), "c": round(max(0.01, (leg["bid"] + leg["ask"]) / 2 * left), 2)})
        options[occ("SPY", day, leg["type"], leg["strike"])] = rows
    return {"stock": stock, "options": options}


def test_a_replayed_quiet_day_takes_profit():
    day = date(2026, 10, 26)
    r = Replay("SPY", day, bars=bars_for_a_quiet_day(day))
    said = []
    rule, made = condor.run(r, r, S, say=said.append)
    assert rule == "take_profit" and made > 0
    assert any("waiting for 10:00" in l for l in said)


def test_a_replay_clock_and_prices():
    day = date(2026, 10, 26)
    r = Replay("SPY", day, bars=bars_for_a_quiet_day(day))
    assert r.now().hour == 9 and r.price() == 760.0
    r.sleep_until("10:00")
    assert r.now().hour == 10 and sym("C", 760) in r.quotes([sym("C", 760)])
    assert len(r.chain()) == 62


def test_ctrl_c_stops_with_one_line_not_a_traceback(monkeypatch, capsys):
    def stopped(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(condor, "run", stopped)
    monkeypatch.setattr(condor.sys, "argv", ["condor.py", "--trade"])
    try:
        condor.main()
    except SystemExit as e:
        assert e.code == 130
    out = capsys.readouterr().out
    assert "stays open in the account" in out and "Traceback" not in out
