"""One run of the wheel, on an Alpaca paper account.

  uv run wheel.py                    look, decide, print - a dry run, nothing is sent
  uv run wheel.py --trade            the same, and place the orders
  uv run wheel.py --picker list      pick from your own list this time (or screen, or your own file)
  uv run wheel.py --set filters.rsi.below=40     change one setting of wheel.toml for this run
  uv run wheel.py --no-new           only look after the stocks already in the wheel

Each run reads the account and, for every stock already in the wheel, takes profit, rolls, sells a
covered call on shares it holds, or lets things run (decide.py). Then, if there is room, the picker
names stocks, each one's put nearest the target delta is found, they are ranked by what the put
pays for the cash it ties up, and the best get a cash-secured put. Settings: wheel.toml."""
import argparse
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import broker
import decide
import pickers
import rank
from market import Market

HERE = Path(__file__).parent
SHOW = 8          # ranked puts printed; the rest are counted


def say(line=""):
    print(line, flush=True)


def money(x):
    return f"${x:,.0f}"


def describe(c, s):
    """One contract on one line: what it is, what it pays, for how much cash."""
    return (f"{c['strike']:>6g} {'put ' if c['symbol'][-9] == 'P' else 'call'} {c['expiry']:%d %b} {s['days']:>2}d  "
            f"delta {abs(c['delta']):.2f}  premium {money(s['premium']):>6}  cash {money(s['cash']):>7}  "
            f"{s['yearly']:4.0%}/yr")


def best_option(stock, kind, rules, today, **limits):
    return rank.choose(broker.option_contracts(stock, kind, today, rules["min_days"], rules["max_days"]),
                       today, rules, **limits)


OPEN = ("new", "accepted", "pending_new", "partially_filled")


def place(trade, verb, option, qty, quote, side, sender, orders):
    """Print what would be sent; send it with --trade. While it does not fill, walk the price
    toward the bid (a sell) or the ask (a buy), a step at a time ([orders] walk_steps), reading the
    quote again before each step: the market moves while an order waits."""
    how, steps, past = orders.get("price", "mid"), orders.get("walk_steps", 0), orders.get("walk_past", 0)
    price = rank.walk(quote, side, how, steps)[0]
    line = f"    {verb} {qty} {option} at {price:.2f}"
    if not trade:
        say(line + "   (dry run)")
        return None
    order = sender(option, qty, price)
    say(line + f"   -> order {order['status']}")
    if steps <= 0:
        return order
    wait = orders.get("walk_seconds", 20)
    for k in range(1, steps + past + 1):
        if broker.wait_order(order["id"], wait)["status"] not in OPEN:
            break
        ladder = rank.walk({**broker.option_quote(option), "penny": quote.get("penny", True)}, side, how, steps, past)
        new = ladder[min(k, len(ladder) - 1)]
        new = min(new, price) if side == "sell" else max(new, price)     # never back the other way
        if new == price:
            continue
        price = new
        order = broker.replace_price(order["id"], price)
        say(f"    not filled in {wait}s - asking {price:.2f}   -> order {order['status']}")
    now = broker.wait_order(order["id"], wait)
    if now["status"] == "filled":
        say(f"    filled at {float(now['filled_avg_price']):.2f}")
    else:
        say(f"    {now['status']} - it stays up for the day; the next run sees it")
    return now


def handle(action, settings, today, trade):
    """Carry out one action on a stock already in the wheel."""
    say(f"  {action.symbol:<6} {action.do:<10} {action.why}")
    if action.do == "buy back" or action.do == "roll":
        q = broker.option_quote(action.option.symbol)
        order = place(trade, "buy to close", action.option.symbol, action.qty, {**q, "penny": True}, "buy",
                      broker.buy_to_close, settings.get("orders", {}))
        if action.do == "buy back":
            return
        if trade and order["status"] != "filled" and not broker.wait_filled(order["id"]):
            say("    not filled yet - the next run sells the new one")
            return
        kind = action.option.kind
        rules = settings[kind]
        limits = {"strike_max": action.option.strike} if kind == "put" else {}
        if kind == "call" and rules["at_or_above_cost"]:
            limits["strike_min"] = action.cost
        new, why = best_option(action.symbol, kind, rules, today, **limits)
        if new is None:
            say(f"    no new {kind}: {why} - the next run tries again")
            return
        say(f"    new {kind}: " + describe(new, rank.score(new, today)))
        place(trade, "sell to open", new["symbol"], action.qty, new, "sell", broker.sell_to_open,
              settings.get("orders", {}))
    elif action.do == "sell call":
        rules = settings["call"]
        limits = {"strike_min": action.cost} if rules["at_or_above_cost"] else {}
        c, why = best_option(action.symbol, "call", rules, today, **limits)
        if c is None:
            say(f"    no call yet: {why} - holding the shares")
            return
        say("    " + describe(c, rank.score(c, today)))
        place(trade, "sell to open", c["symbol"], action.qty, c, "sell", broker.sell_to_open,
              settings.get("orders", {}))


def new_puts(settings, today, trade, picker, buying_power, positions, orders):
    room, in_wheel = decide.room_for_puts(positions, orders, settings)
    if room == 0:
        say("No room for a new put this run (put.max_stocks, put.new_per_run).")
        return
    say(f"Picking stocks with: {picker}")
    market = Market(settings, today)
    picks = [s for s in pickers.load(picker).pick(market, settings, say) if s not in in_wheel]
    if not picks:
        say("Nothing passes today - no new put.")
        return
    rules = settings["put"]
    cash = min(rules["max_cash"], buying_power)
    say(f"Puts near delta {rules['delta']:.2f}, {rules['min_days']}-{rules['max_days']} days out, "
        f"setting aside at most {money(cash)}:")
    chosen, skipped = [], {}
    for stock in picks:
        c, why = best_option(stock, "put", rules, today, strike_max=cash / 100)
        if c is None:
            skipped.setdefault(why, []).append(stock)
        chosen.append((stock, c))
    for why, stocks in skipped.items():
        say(f"  skip   {' '.join(stocks)}: {why}")
    ranked = rank.rank(chosen, today)
    for i, (stock, c, s) in enumerate(ranked[:SHOW]):
        notes = " ".join(f"{k} {v}" for k, v in market.notes.get(stock, {}).items())
        star = "*" if i < room else " "                # the ones this run sells
        say(f"{star} {stock:<6}" + describe(c, s) + (f"  {notes}" if notes else ""))
    if len(ranked) > SHOW:
        say(f"  ... and {len(ranked) - SHOW} more")
    for stock, c, s in ranked[:room]:
        say(f"Best: {stock} - sell the {c['strike']:g} put, setting aside {money(s['cash'])}")
        place(trade, "sell to open", c["symbol"], 1, c, "sell", broker.sell_to_open, settings.get("orders", {}))


def override(settings, assignment):
    """'filters.rsi.below=40' or 'screen.filters=market_cap,rsi' -> settings changed for this run.
    The value is read as TOML (a number, true/false), or as a list of names where a list was."""
    key, _, text = assignment.partition("=")
    *path, last = key.strip().split(".")
    table = settings
    for part in path:
        table = table.setdefault(part, {})
    if isinstance(table.get(last), list):
        value = [v.strip() for v in text.split(",") if v.strip()]
    else:
        try:
            value = tomllib.loads(f"v = {text}")["v"]
        except tomllib.TOMLDecodeError:
            value = text
    table[last] = value
    return settings


def main(argv=None):
    ap = argparse.ArgumentParser(description="One run of the wheel on an Alpaca paper account.")
    ap.add_argument("--trade", action="store_true", help="place the orders (default: a dry run)")
    ap.add_argument("--picker", help="list, screen, or your own file in pickers/")
    ap.add_argument("--no-new", action="store_true", help="no new puts this run")
    ap.add_argument("--config", default=str(HERE / "wheel.toml"))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="change one setting for this run, e.g. filters.rsi.below=40")
    args = ap.parse_args(argv)
    settings = tomllib.loads(Path(args.config).read_text())
    for assignment in args.set:
        override(settings, assignment)
    today = datetime.now(ZoneInfo("America/New_York")).date()

    say(f"Wheel bot - paper account - {today:%a %d %b %Y} - "
        + ("TRADING" if args.trade else "dry run (add --trade to place orders)"))
    acct = broker.account()
    say(f"Cash {money(acct['cash'])}, options buying power {money(acct['options_buying_power'])}")
    if args.trade and not broker.market_open():
        say("The market is closed: orders wait for the open.")
    positions, orders = broker.positions(), broker.open_orders()

    actions = decide.decide(positions, orders, settings, today)
    say("In the wheel now:" + ("" if actions else " nothing"))
    for action in actions:
        handle(action, settings, today, args.trade)
    if args.no_new:
        return
    say()
    try:
        new_puts(settings, today, args.trade, args.picker or settings["picker"],
                 acct["options_buying_power"], positions, orders)
    except RuntimeError as e:          # a data source said no: say why, in one line
        say(f"No new put this run: {e}")


if __name__ == "__main__":
    main()
