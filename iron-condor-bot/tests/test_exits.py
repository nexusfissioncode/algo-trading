"""Every exit rule, and the order they are checked in."""
from datetime import datetime
from zoneinfo import ZoneInfo

import exits
from helpers import condor, quotes_for

NY = ZoneInfo("America/New_York")
RULES = {"take_profit": 0.5, "stop": 2.0, "touch": True, "close_by": "15:15"}


def at(h, m):
    return datetime(2026, 10, 26, h, m, tzinfo=NY)


def test_cost_to_close_buys_the_shorts_back_and_sells_the_wings():
    c = condor()
    assert exits.cost_to_close(c, quotes_for(c, 0.9, 0.2, 0.8, 0.1)) == 1.4


def test_cost_to_close_is_none_when_a_leg_has_no_quote():
    c = condor()
    q = quotes_for(c, 0.9, 0.2, 0.8, 0.1)
    q.pop(c["legs"]["long_call"]["symbol"])
    assert exits.cost_to_close(c, q) is None


def test_holds_in_the_middle_of_the_day():
    assert exits.check(condor(), 0.8, 760, at(12, 0), RULES) is None


def test_take_profit_fires_when_half_the_credit_is_kept():
    rule, why = exits.check(condor(), 0.5, 760, at(12, 0), RULES)
    assert rule == "take_profit" and "at or under 0.50" in why


def test_stop_fires_at_twice_the_credit():
    rule, why = exits.check(condor(), 2.0, 760, at(12, 0), RULES)
    assert rule == "stop" and "at or over 2.00" in why


def test_touch_fires_at_either_short_strike():
    assert exits.check(condor(), 1.2, 755.0, at(12, 0), RULES)[0] == "touch"
    assert exits.check(condor(), 1.2, 765.4, at(12, 0), RULES)[0] == "touch"


def test_touch_can_be_switched_off():
    assert exits.check(condor(), 1.2, 755.0, at(12, 0), {**RULES, "touch": False}) is None


def test_close_by_fires_at_the_closing_time_whatever_happens():
    rule, why = exits.check(condor(), 0.8, 760, at(15, 15), RULES)
    assert rule == "close_by" and "15:15" in why


def test_close_by_fires_even_without_a_quote():
    assert exits.check(condor(), None, 760, at(15, 20), RULES)[0] == "close_by"


def test_the_first_rule_in_the_list_wins():
    assert exits.check(condor(), 0.4, 755.0, at(15, 30), RULES)[0] == "take_profit"
    assert exits.check(condor(), 2.5, 755.0, at(15, 30), RULES)[0] == "stop"
    assert exits.check(condor(), 1.2, 755.0, at(15, 30), RULES)[0] == "touch"


def test_dollars_made_and_lost_for_one_contract():
    assert exits.pnl(condor(), 0.5, 1) == 50.0
    assert exits.pnl(condor(), 2.0, 1) == -100.0
    assert exits.pnl(condor(), 0.5, 3) == 150.0
