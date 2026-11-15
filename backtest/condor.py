"""A same-day iron condor on SPY, on an Alpaca paper account.

  uv run condor.py                       today's condor: price, straddle, strikes - a dry run, nothing is sent
  uv run condor.py --trade               open it at the entry time, watch it, close it by the rules
  uv run condor.py --replay 2026-10-23   run a past day on its real prices (nothing is sent)
  uv run condor.py --close-now           close today's open condor now, whatever the rules say
  uv run condor.py --set exits.stop=3    change one setting of condor.toml for this run

At the entry time it prices the at-the-money straddle, sets the short strikes about the expected
move either side of the price and the wings a fixed width further out (strikes.py), and opens all
four legs as one order. Then it looks every few seconds and closes the condor on the first exit
rule that fires (exits.py), walking the buy-back price until it fills (closer.py). If the program
stops and starts again, it finds the open condor in the account and carries on watching."""
import argparse
import sys
import tomllib
from datetime import date
from pathlib import Path

import broker
import closer
import exits
import strikes
from market import Live, Replay

HERE = Path(__file__).parent


def say(line=""):
    print(line, flush=True)


def money(x):
    return f"-${-x:,.0f}" if x < 0 else f"+${x:,.0f}"


def settings(path=HERE / "condor.toml", changes=()):
    s = tomllib.loads(Path(path).read_text())
    for change in changes:
        key, value = change.split("=", 1)
        *parents, last = key.split(".")
        node = s
        for p in parents:
            node = node[p]
        try:
            node[last] = tomllib.loads(f"v = {value}")["v"]
        except tomllib.TOMLDecodeError:          # a bare word or a time: keep it as text
            node[last] = value
    return s


def from_positions(positions, stock, day):
    """Today's open condor, rebuilt from the account's positions (so a restart carries on), or None.
    The credit is what the shorts were sold for less what the wings cost."""
    tag = f"{stock}{day:%y%m%d}"
    legs = {}
    for p in positions:
        s = p["symbol"]
        if not s.startswith(tag) or len(s) != len(tag) + 9:
            continue
        short = float(p["qty"]) < 0
        name = ("short_" if short else "long_") + ("call" if broker.kind(s) == "C" else "put")
        legs[name] = {"symbol": s, "strike": broker.strike(s), "entry": float(p["avg_entry_price"]),
                      "qty": abs(int(float(p["qty"])))}
    if len(legs) != 4:
        return None
    credit = legs["short_put"]["entry"] + legs["short_call"]["entry"] - legs["long_put"]["entry"] - legs["long_call"]["entry"]
    return {"legs": legs, "credit": round(credit, 2), "contracts": legs["short_put"]["qty"]}


def show(pick, rules, contracts, say=say):
    s, legs = pick["straddle"], pick["legs"]
    say(f"  straddle {s['strike']:g}: call {strikes.mid(s['call']):.2f} + put {strikes.mid(s['put']):.2f} = {s['cost']:.2f}"
        f"   expected move {pick['move']:.2f}")
    say(f"  the condor   buy {legs['long_put']['strike']:g} put   sell {legs['short_put']['strike']:g} put"
        f"   sell {legs['short_call']['strike']:g} call   buy {legs['long_call']['strike']:g} call")
    say(f"  credit {pick['credit']:.2f} at the mids (${pick['credit'] * 100 * contracts:,.0f})"
        f"   most it can lose ${pick['max_loss'] * 100 * contracts:,.0f}"
        f"   breakevens {pick['breakevens'][0]:g} and {pick['breakevens'][1]:g}")
    t = exits.targets(pick, rules)
    say(f"  exits   take profit at {t['take_profit']:.2f}   stop at {t['stop']:.2f}"
        + (f"   touch {legs['short_put']['strike']:g} or {legs['short_call']['strike']:g}" if rules.get("touch") else "")
        + f"   close by {rules['close_by']}")


def enter(pick, contracts, entry, sender, say):
    """Open the condor at the mid; halfway to the natural price if it has not filled; give up after
    that. The credit it filled at, or None."""
    credit = pick["credit"]
    order = sender.open_condor(pick, contracts, credit)
    say(f"  sell the condor at {credit:.2f}   -> order {order['status']}")
    now = sender.wait_order(order["id"], entry["fill_seconds"] / 2)
    if now["status"] != "filled":
        lower = round(max(entry["least_credit"], (credit + pick["natural"]) / 2), 2)
        if lower < credit:
            order = sender.replace_credit(order["id"], lower)
            say(f"  not filled - asking {lower:.2f}   -> order {order['status']}")
        now = sender.wait_order(order["id"], entry["fill_seconds"] / 2)
    if now["status"] != "filled":
        sender.cancel(order["id"])
        say("  not filled - cancelled. No condor today.")
        return None
    fill = abs(float(now["filled_avg_price"]))
    say(f"  filled at {fill:.2f}: ${fill * 100 * contracts:,.0f} in")
    return fill


def watch(condor, contracts, market, sender, s, say, close_now=False):
    """Look, check the rules, close on the first that fires. Returns (rule, dollars) when closed."""
    rules, every = s["exits"], s["watch"]["every"]
    print_every = 1800 if market.replay else s["watch"]["print_every"]
    t = exits.targets(condor, rules)
    say(f"  {'time':<6} {s['underlying']:<8} {'buy back':>8} {'P&L':>7}   take profit {t['take_profit']:.2f}  stop {t['stop']:.2f}")
    last_print = None
    while True:
        now, price = market.now(), market.price()
        cost = exits.cost_to_close(condor, market.quotes([leg["symbol"] for leg in condor["legs"].values()]))
        fired = ("by hand", "--close-now") if close_now else exits.check(condor, cost, price, now, rules)
        if cost is not None and (fired or last_print is None or (now - last_print).total_seconds() >= print_every):
            say(f"  {now:%H:%M}  {price:<8.2f} {cost:>8.2f} {money(exits.pnl(condor, cost, contracts)):>7}")
            last_print = now
        if fired:
            say(f"  exit: {fired[0]} - {fired[1]}")
            fill = closer.close(condor, contracts, market, sender, s["orders"], say)
            if fill is not None:
                made = exits.pnl(condor, fill, contracts)
                say(f"  closed: {money(made)} on ${condor['credit'] * 100 * contracts:,.0f} of credit")
                return fired[0], made
        if market.replay and market.finished():
            say("  the market closed with the condor still open")
            return None, None
        market.sleep(60 if market.replay else every)


def run(market, sender, s, trade=False, close_now=False, positions=lambda: [], say=say):
    stock, contracts, rules = s["underlying"], s["contracts"], s["exits"]
    day = market.today()
    mode = "a replay of a past day, on its real prices" if market.replay else ("trading, paper account" if trade or close_now else "a dry run, nothing is sent")
    say(f"{stock} iron condor, {day:%a %d %b %Y} - {mode}")
    held = None if market.replay else from_positions(positions(), stock, day)
    if held:
        say(f"  found an open condor: {held['legs']['long_put']['strike']:g} / {held['legs']['short_put']['strike']:g} puts,"
            f" {held['legs']['short_call']['strike']:g} / {held['legs']['long_call']['strike']:g} calls, sold for {held['credit']:.2f}")
        if not trade and not close_now:
            say("  (dry run: not watching it - add --trade)")
            return held
        return watch(held, held["contracts"], market, sender, s, say, close_now)
    if close_now:
        say("  no open condor today - nothing to close")
        return None
    if market.now().time() < exits.hhmm(s["entry"]["at"]) and (trade or market.replay):
        say(f"  waiting for {s['entry']['at']} New York")
        market.sleep_until(s["entry"]["at"])
    if market.now().time() >= exits.hhmm(rules["close_by"]):
        say(f"  it is past {rules['close_by']}: too late to open one today")
        return None
    price = market.price()
    say(f"  {market.now():%H:%M}  {stock} {price:.2f}")
    pick, why = strikes.choose(market.chain(), price, s["entry"]["move_factor"], s["entry"]["wing"])
    if not pick:
        say(f"  no condor today: {why}")
        return None
    show(pick, rules, contracts, say)
    if pick["credit"] < s["entry"]["least_credit"]:
        say(f"  pays less than {s['entry']['least_credit']:.2f}: no condor today")
        return None
    if not trade and not market.replay:
        say("  (dry run: nothing sent - add --trade)")
        return pick
    fill = enter(pick, contracts, s["entry"], sender, say)
    if fill is None:
        return None
    return watch({**pick, "credit": fill}, contracts, market, sender, s, say)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trade", action="store_true", help="send orders to the paper account")
    ap.add_argument("--replay", metavar="DATE", help="run a past day (YYYY-MM-DD) on its real prices")
    ap.add_argument("--close-now", action="store_true", help="close today's open condor now")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="change a setting for this run")
    a = ap.parse_args()
    s = settings(changes=a.set)
    try:
        if a.replay:
            r = Replay(s["underlying"], date.fromisoformat(a.replay), broker)
            run(r, r, s)
        else:
            run(Live(s["underlying"], broker), broker, s, trade=a.trade, close_now=a.close_now, positions=broker.positions)
    except KeyboardInterrupt:      # Ctrl-C: stop quietly; an open condor stays in the account, and the next run finds it
        say("\n  stopped: anything open stays open in the account - run it again to carry on")
        sys.exit(130)


if __name__ == "__main__":
    main()
