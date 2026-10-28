"""Picking stocks - your list, the screen, its filters, the SEC's share counts - and the daily
script, on made-up data. Nothing here talks to Alpaca or the SEC."""
import tomllib
from datetime import date
from pathlib import Path

import sec
from filters import above_200, market_cap, rsi
from market import Market
from pickers import list as list_picker
from pickers import screen

SETTINGS = tomllib.loads((Path(__file__).parent.parent / "wheel.toml").read_text())
TODAY = date(2026, 10, 21)


# --- picking the stocks -------------------------------------------------------------------------

class FakeData:
    """Stands in for broker.py: six stocks, their prices and their closing prices."""
    def __init__(self):
        self.close = {"BIG": [100 - i * 0.5 for i in range(80)],      # falling: oversold
                      "HUGE": [100 + i * 0.5 for i in range(80)],     # rising
                      "SMALL": [100 - i * 0.5 for i in range(80)]}

    def stocks_with_options(self):
        return [{"symbol": s, "name": s} for s in ("BIG", "HUGE", "SMALL")]

    def prices(self, symbols):
        return {s: self.close[s][-1] for s in symbols}

    def closes(self, symbols, days):
        return {s: self.close[s][-days:] for s in symbols}


def fake_market():
    m = Market(SETTINGS, TODAY, source=FakeData())
    m._shares = {"BIG": {"shares": 5e9}, "HUGE": {"shares": 5e9}, "SMALL": {"shares": 1e8}}
    return m


def test_rsi_of_a_steady_fall_is_low_and_of_a_steady_rise_is_high():
    assert rsi.rsi([100 - i for i in range(30)]) == 0.0
    assert rsi.rsi([100 + i for i in range(30)]) == 100.0
    assert 40 < rsi.rsi([100, 101, 100, 101, 100, 101] * 5) < 60


def test_rsi_matches_a_worked_example():
    # Seven days up two dollars, seven days down one: average gain 14/14 = 1, average loss 7/14 = 0.5,
    # so RS = 2 and RSI = 100 - 100/3 = 66.67. One more day up a dollar: gain (1x13 + 1)/14 = 1,
    # loss (0.5x13 + 0)/14 = 0.4643, RS = 2.154, RSI = 68.29.
    closes = [100]
    for up in [True, False] * 7:
        closes.append(closes[-1] + (2 if up else -1))
    assert round(rsi.rsi(closes), 2) == 66.67
    assert round(rsi.rsi(closes + [closes[-1] + 1]), 2) == 68.29


def test_market_cap_keeps_the_big_companies():
    assert market_cap.apply(["BIG", "HUGE", "SMALL"], fake_market(), {"min_dollars": 100e9}) == \
        ["BIG", "HUGE"]


def test_the_screen_runs_its_filters_in_order():
    lines = []
    picks = screen.pick(fake_market(), {**SETTINGS, "screen": {"filters": ["market_cap", "rsi"]}},
                        lines.append)
    assert picks == ["BIG"]
    assert [line.split()[0] for line in lines] == ["start", "market_cap", "rsi"]


def test_your_own_filter_drops_in():
    assert above_200.apply(["BIG", "HUGE"], fake_market(), {"days": 50}) == ["HUGE"]


def test_your_list_is_used_as_written():
    picks = list_picker.pick(fake_market(), {"list": {"symbols": ["aapl", "KO"]}}, lambda _: None)
    assert picks == ["AAPL", "KO"]


# --- the SEC's share counts ---------------------------------------------------------------------

def test_quarters_count_back_from_today():
    assert sec.recent_quarters(date(2026, 10, 21)) == ["CY2026Q4", "CY2026Q3", "CY2026Q2", "CY2026Q1"]
    assert sec.recent_quarters(date(2027, 1, 5), 2) == ["CY2027Q1", "CY2026Q4"]


def test_share_counts_join_tickers_and_fall_back_to_the_average():
    tickers = sec.parse_tickers("aapl\t320193\ngoogl\t1652044\ngoog\t1652044\ntm\t1094517\n")
    cover = [{"data": [{"cik": 320193, "val": 14.6e9, "end": "2026-07-17", "loc": "US-CA"},
                       {"cik": 1094517, "val": 13.0e9, "end": "2026-03-31", "loc": "JP-"}]}]
    average = [{"data": [{"cik": 1652044, "val": 12.2e9, "end": "2026-06-30", "loc": "US-CA"},
                         {"cik": 320193, "val": 1.0, "end": "2026-06-27", "loc": "US-CA"}]}]
    got = sec.join(cover, average, tickers)
    assert got["AAPL"]["shares"] == 14.6e9 and got["AAPL"]["source"] == "cover"
    assert got["GOOGL"] == got["GOOG"] and got["GOOG"]["source"] == "average"
    assert "TM" not in got                                     # a foreign company, left out
    assert "TM" in sec.join(cover, average, tickers, us_only=False)


def test_the_newest_quarter_wins():
    tickers = sec.parse_tickers("aapl\t320193\n")
    newer = {"data": [{"cik": 320193, "val": 2.0, "end": "2026-07-17", "loc": "US-CA"}]}
    older = {"data": [{"cik": 320193, "val": 1.0, "end": "2026-04-17", "loc": "US-CA"}]}
    assert sec.join([newer, older], [], tickers)["AAPL"]["shares"] == 2.0


def test_the_sec_needs_your_name():
    try:
        sec.share_counts("Your Name your-email@example.com", TODAY)
    except RuntimeError as e:
        assert "sec_user_agent" in str(e)
    else:
        raise AssertionError("ran with the placeholder User-Agent")


# --- the daily script ---------------------------------------------------------------------------

def test_the_daily_script_refuses_to_run_without_its_keys(tmp_path):
    import shutil
    import subprocess
    script = tmp_path / "run-wheel.sh"
    shutil.copy(Path(__file__).parent.parent / "run-wheel.sh", script)
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert r.returncode == 1 and "no keys.env" in r.stderr
    assert not (tmp_path / "runs.log").exists()


def test_one_setting_can_change_for_one_run():
    import copy
    import wheel
    s = wheel.override(copy.deepcopy(SETTINGS), "filters.rsi.below=40")
    s = wheel.override(s, "screen.filters=market_cap,rsi,above_200")
    s = wheel.override(s, "picker=list")
    assert s["filters"]["rsi"]["below"] == 40
    assert s["screen"]["filters"] == ["market_cap", "rsi", "above_200"]
    assert s["picker"] == "list" and SETTINGS["filters"]["rsi"]["below"] == 30


# --- what the market cap filter sees ------------------------------------------------------------

def test_market_cap_is_shares_times_price_or_says_why_not():
    import marketcap
    counts = {"WMT": {"shares": 8.0e9, "as_of": "2026-08-29", "source": "cover"},
              "AAPL": {"shares": 14.6e9, "as_of": "2026-07-17", "source": "cover"}}
    assert marketcap.line("WMT", counts, {"WMT": 117.73}) == \
        "WMT      8,000,000,000 shares (cover, 2026-08-29) x $117.73 = $942 billion"
    assert marketcap.line("AAPL", counts, {"AAPL": 343.94}).endswith("= $5.02 trillion")
    assert "foreign" in marketcap.line("TM", counts, {})
    assert marketcap.line("WMT", counts, {}) == "WMT    no price from Alpaca"


def test_when_the_sec_refuses_the_last_saved_copy_is_used(tmp_path, monkeypatch):
    import urllib.error
    monkeypatch.setattr(sec, "CACHE", tmp_path)
    def refuse(url, agent):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(sec, "_get", refuse)
    (tmp_path / "2026-10-19-ticker.txt").write_text("aapl\t320193\n")
    assert sec._cached("ticker.txt", "https://www.sec.gov/include/ticker.txt", "me", date(2026, 10, 21)) == "aapl\t320193\n"
    try:
        sec._cached("frame.json", "https://data.sec.gov/x", "me", date(2026, 10, 21))
    except RuntimeError as e:
        assert "refused" in str(e) and "sec_user_agent" in str(e)
    else:
        raise AssertionError("no saved copy, and still no error")
