"""Choosing the option and ranking the puts, on made-up contracts."""
import tomllib
from datetime import date, timedelta
from pathlib import Path

import rank

SETTINGS = tomllib.loads((Path(__file__).parent.parent / "wheel.toml").read_text())
TODAY = date(2026, 10, 21)


# --- choosing the option ------------------------------------------------------------------------

def contract(strike, delta, bid, ask, days=30, oi=500, penny=True):
    return {"symbol": f"X{strike}", "strike": strike, "expiry": TODAY + timedelta(days=days), "delta": delta,
            "bid": bid, "ask": ask, "open_interest": oi, "penny": penny}


def test_the_put_nearest_the_target_delta_is_chosen():
    c, why = rank.choose([contract(45, -0.18, .3, .32), contract(49, -0.29, .64, .66),
                          contract(50, -0.38, .9, .92)], TODAY, SETTINGS["put"])
    assert c["strike"] == 49 and why is None


def test_a_put_too_far_from_the_target_is_refused():
    c, why = rank.choose([contract(40, -0.07, .1, .11)], TODAY, SETTINGS["put"])
    assert c is None and why == "delta too far from the target"


def test_a_put_that_needs_too_much_cash_says_how_much():
    c, why = rank.choose([contract(330, -0.30, 5, 5.2)], TODAY, SETTINGS["put"], strike_max=300)
    assert c is None and "$33,000" in why


def test_thin_or_wide_options_are_refused():
    rules = SETTINGS["put"]
    assert rank.why_not(contract(49, -0.3, .6, .7, oi=10), TODAY, rules) == "too little open interest"
    assert rank.why_not(contract(49, -0.3, .4, .7), TODAY, rules) == "bid and ask too far apart"
    assert rank.why_not(contract(49, -0.3, 0, .7), TODAY, rules) == "nobody is bidding"
    assert rank.why_not(contract(49, -0.3, .6, .62, days=60), TODAY, rules) == "outside the days window"


def test_a_call_is_never_below_what_the_shares_cost():
    c, _ = rank.choose([contract(48, 0.30, .9, .92), contract(52, 0.24, .5, .52)], TODAY,
                       SETTINGS["call"], strike_min=49.0)
    assert c["strike"] == 52


def test_puts_are_ranked_by_what_they_pay_for_a_year():
    a = contract(49, -0.3, .64, .66, days=30)       # 1.3% in 30 days
    b = contract(115, -0.3, 2.73, 2.87, days=44)    # 2.4% in 44 days
    assert [s for s, _, _ in rank.rank([("BAC", a), ("WMT", b), ("KO", None)], TODAY)] == ["WMT", "BAC"]


def test_limit_prices_never_go_past_the_mid():
    c = contract(49, -0.3, .63, .66)
    assert rank.limit_price(c, "sell") == 0.64 and rank.limit_price(c, "buy") == 0.65
    assert rank.limit_price(contract(115, -.3, 3.1, 3.3), "sell") == 3.20                 # five-cent steps
    assert rank.limit_price(c, "sell", "natural") == 0.63
