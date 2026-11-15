"""Where the four strikes go: the straddle, the expected move, the wings."""
import strikes
from helpers import chain, leg


def test_the_straddle_is_the_nearest_strike_with_both_sides_quoted():
    s = strikes.straddle(chain(760), 760.3)
    assert s["strike"] == 760
    assert s["cost"] == 6.0                    # call 3.00 + put 3.00 at the mids


def test_a_strike_with_one_side_unquoted_is_skipped():
    c = [x for x in chain(760) if not (x["strike"] == 760 and x["type"] == "P")]
    assert strikes.straddle(c, 760.1)["strike"] in (759, 761)


def test_short_strikes_sit_at_the_expected_move_either_side():
    pick, why = strikes.choose(chain(760, half=15), 760, 0.85, 5)
    assert why is None
    assert pick["move"] == 5.1                 # 6.00 x 0.85
    assert pick["legs"]["short_put"]["strike"] == 754      # at or below 760 - 5.1
    assert pick["legs"]["short_call"]["strike"] == 766     # at or above 760 + 5.1


def test_wings_are_a_whole_width_further_out():
    pick, _ = strikes.choose(chain(760, half=15), 760, 0.85, 5)
    assert pick["legs"]["long_put"]["strike"] == 749
    assert pick["legs"]["long_call"]["strike"] == 771
    assert pick["width"] == 5


def test_credit_most_it_can_lose_and_breakevens():
    pick, _ = strikes.choose(chain(760, half=15), 760, 0.85, 5)
    legs = pick["legs"]
    credit = round(strikes.mid(legs["short_put"]) + strikes.mid(legs["short_call"])
                   - strikes.mid(legs["long_put"]) - strikes.mid(legs["long_call"]), 2)
    assert pick["credit"] == credit
    assert pick["max_loss"] == round(5 - credit, 2)
    assert pick["breakevens"] == (round(754 - credit, 2), round(766 + credit, 2))
    assert pick["natural"] < pick["credit"]    # selling at the bids pays less than the mids


def test_no_wing_far_enough_out_means_no_condor():
    pick, why = strikes.choose(chain(760, half=10), 760, 0.85, 5)
    assert pick is None and "wing" in why


def test_an_empty_chain_means_no_condor():
    pick, why = strikes.choose([leg("C", 760, 0, 0)], 760, 0.85, 5)
    assert pick is None and "quoted" in why
