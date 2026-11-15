"""Run the bot's own code over every past day, and report it without flattering it.

  uv run backtest.py fetch                  every day's one-minute bars, saved in .cache/
  uv run backtest.py run                    the settings in condor.toml, every day, no cost
  uv run backtest.py run --skip-wide 10:00  skip wide days, judged by what is known at that time
  uv run backtest.py costs                  the same run at a range of costs a fill
  uv run backtest.py sweep                  every setting in sweep.toml, chosen on one period, judged on the next
  uv run backtest.py walk                   choose on 12 months, trade the next 6, again and again
  uv run backtest.py report                 all of it on one screen

Add --symbol QQQ for another underlying, --set exits.touch=false to change a setting, --cost 0.01
for a cost in dollars on each leg, each way. Nothing here places an order."""
import argparse
import gc
import itertools
import json
import multiprocessing
import os
import pickle
import random
import statistics
import sys
import tomllib
from collections import Counter, namedtuple
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

import condor
from market import CACHE, BAR, NY, Replay

HERE = Path(__file__).parent
FILLS_CLOSED, FILLS_SETTLED = 8, 4      # four legs in and out; left to expiry, only the way in
SKIP_SHARE = 0.30                             # --skip-wide skips about this share of days
LOOKBACK = 60                           # compared with this many days before it, never with later ones
CENTS = (0, 0.005, 0.01, 0.015, 0.02, 0.03)
COINS_SEED = 1

Trade = namedtuple("Trade", "day rule made fills credit")


def usd(x):
    return condor.money(x)


def short(d):
    return f"{d.day} {d:%b %Y}"


# --- the days --------------------------------------------------------------------------------------

class Day(Replay):
    """One past day, sharing bars already read, and remembering the condor it opened. Everything
    the bot sees still comes from Replay."""

    def __init__(self, stock, day, prepared):
        self.stock, self.day = stock, day
        self.spy, self.opts = prepared
        self.clock = datetime(day.year, day.month, day.day, 9, 30, tzinfo=NY)
        self.orders, self.next_id = {}, 1
        self.held = None

    def open_condor(self, condor, qty, credit):
        self.held = {**condor, "credit": credit}
        return super().open_condor(condor, qty, credit)


def trading_days(start="2024-02-01", until=None):
    import broker
    from alpaca.trading.requests import GetCalendarRequest
    end = date.fromisoformat(until) if until else date.today() - timedelta(days=1)
    rows = broker.trading().get_calendar(GetCalendarRequest(start=date.fromisoformat(start), end=end))
    return [date.fromisoformat(str(r["date"])[:10]) for r in rows]


def fetch(symbol, until=None):
    """Reading a day through Replay saves it, so the backtest reads what a replay reads."""
    import broker
    days = trading_days(until=until)
    print(f"{symbol}: {len(days)} trading days since {short(days[0])}, one minute at a time", flush=True)
    missing = []
    for i, d in enumerate(days, 1):
        try:
            Replay(symbol, d, broker)
        except SystemExit as e:
            missing.append(str(d))
            print(f"  {d}  {e}", flush=True)
        if i % 50 == 0 or i == len(days):
            print(f"  {i:>4} of {len(days)}   {d}", flush=True)
    (CACHE / f"{symbol}.missing").write_text(json.dumps(missing))
    print(f"saved in {CACHE.name}/", flush=True)


def left_out(symbol):
    """Trading days the fetch could find no bars for, so that no report can hide them."""
    f = CACHE / f"{symbol}.missing"
    return json.loads(f.read_text()) if f.exists() else []


def load(symbol):
    """Every saved day of one symbol, ready to run: {date: (stock, options)}."""
    files = sorted(CACHE.glob(f"{symbol}-20*.json"))
    if not files:
        raise SystemExit(f"nothing saved for {symbol}: run  uv run backtest.py fetch --symbol {symbol}")
    ready = CACHE / f"{symbol}.ready"
    if ready.exists() and ready.stat().st_mtime >= max(f.stat().st_mtime for f in files):
        with ready.open("rb") as f:
            return pickle.load(f)
    days = {}
    for f in files:
        r = Replay(symbol, date.fromisoformat(f.stem[len(symbol) + 1:]), bars=json.loads(f.read_text()))
        days[r.day] = (r.spy, r.opts)
    with ready.open("wb") as f:
        pickle.dump(days, f, protocol=5)
    return days


# --- running ---------------------------------------------------------------------------------------

def one_day(symbol, d, prepared, s):
    """The bot's own run on one day. A Trade, or None when it opened nothing. A condor still open
    at the close is settled at what it is worth, never left out."""
    r = Day(symbol, d, prepared)
    got = condor.run(r, r, s, say=lambda *_: None)
    if r.held is None:
        return None
    rule, made = got if isinstance(got, tuple) else (None, None)
    if rule is None:
        return Trade(d, "settled", settle(r.held, r.price()), FILLS_SETTLED, r.held["credit"])
    return Trade(d, rule, made, FILLS_CLOSED, r.held["credit"])


def settle(c, price):
    """Dollars made if a condor runs to the close at this price."""
    legs = c["legs"]
    call = max(0, price - legs["short_call"]["strike"]) - max(0, price - legs["long_call"]["strike"])
    put = max(0, legs["short_put"]["strike"] - price) - max(0, legs["long_put"]["strike"] - price)
    return round((c["credit"] - call - put) * 100, 2)


def run_all(symbol, days, s, skip=frozenset()):
    trades = []
    for d in sorted(days):
        if d not in skip:
            t = one_day(symbol, d, days[d], s)
            if t:
                trades.append(t)
    return trades


def spent(t, cost):
    return t.made - cost * 100 * t.fills


def summary(trades, cost=0.0):
    """Totals, including the worst fall from a high point."""
    if not trades:
        return dict(n=0, total=0, average=0, won=0, worst=0, fall=0)
    made = [spent(t, cost) for t in trades]
    level = high = fall = 0
    for m in made:
        level += m
        high = max(high, level)
        fall = max(fall, high - level)
    return dict(n=len(made), total=sum(made), average=sum(made) / len(made),
                won=100 * sum(m > 0 for m in made) / len(made), worst=min(made), fall=fall)


def wide_days(days, upto):
    """Days to skip because they were wide, judged by the price up to `upto` ("close" uses the
    whole day, which nobody knows at 10:00: that is the mistake it is there to show). Each day is
    compared only with the days before it."""
    stamp = None if upto == "close" else tuple(map(int, upto.split(":")))
    ranges = {}
    for d in sorted(days):
        seconds, closes = days[d][0]
        if stamp is not None:
            cut = datetime(d.year, d.month, d.day, *stamp, tzinfo=NY).timestamp()
            closes = [c for t, c in zip(seconds, closes) if t + BAR <= cut]
        if closes:
            ranges[d] = (max(closes) - min(closes)) / closes[0]
    order, skip = sorted(ranges), set()
    for i, d in enumerate(order):
        before = sorted(ranges[x] for x in order[max(0, i - LOOKBACK):i])
        if len(before) == LOOKBACK and ranges[d] > before[int(LOOKBACK * (1 - SKIP_SHARE))]:
            skip.add(d)
    return skip


def break_even(trades):
    """The cost a fill at which the total reaches zero, or None if it is at or below zero already."""
    made, fills = sum(t.made for t in trades), sum(t.fills for t in trades)
    return made / (100 * fills) if made > 0 and fills else None


# --- settings --------------------------------------------------------------------------------------

def grid(path=HERE / "sweep.toml"):
    """(keys, every combination) from sweep.toml."""
    table = tomllib.loads(Path(path).read_text())
    return list(table), list(itertools.product(*table.values()))


def apply(base, keys, values):
    s = deepcopy(base)
    for key, value in zip(keys, values):
        group, name = key.split(".")
        s[group][name] = value
    return s


def label(keys, values):
    return "  ".join(f"{k.split('.')[1]} {v}" for k, v in zip(keys, values))


def split_day(days):
    order = sorted(days)
    return order[len(order) // 2]


def between(trades, start, end):
    return [t for t in trades if start <= t.day < end]


FAR = date(2100, 1, 1)
NEAR = date(2000, 1, 1)

_days = _symbol = _base = _keys = None


def _one_setting(values):
    return values, run_all(_symbol, _days, apply(_base, _keys, values))


def sweep(symbol, days, base, keys, combos, workers):
    """Every combination over every day, on `workers` processes. The bars are shared, not copied."""
    global _days, _symbol, _base, _keys
    _days, _symbol, _base, _keys = days, symbol, base, keys
    gc.collect()
    gc.freeze()
    out = []
    step = max(1, len(combos) // 8)
    with multiprocessing.get_context("fork").Pool(workers, maxtasksperchild=200) as pool:
        for i, r in enumerate(pool.imap(_one_setting, combos, chunksize=10), 1):
            out.append(r)
            if i % step == 0:
                print(f"  {i:>6,} of {len(combos):,}", flush=True)
    return out


def saved_sweep(symbol):
    f = CACHE / f"{symbol}.sweep"
    if not f.exists():
        return None
    with f.open("rb") as h:
        return pickle.load(h)


def picked(results, start, end, cost):
    """Results, best first, by what each made between two dates."""
    return sorted(results, key=lambda r: -summary(between(r[1], start, end), cost)["total"])


def sweep_findings(results, cut, cost):
    ranked = picked(results, NEAR, cut, cost)
    chosen = [summary(between(r[1], NEAR, cut), cost)["total"] for r in ranked]
    following = [summary(between(r[1], cut, FAR), cost)["total"] for r in ranked]
    return dict(best=ranked[0][0], chosen=chosen[0], next=following[0],
                top20=statistics.mean(following[:20]), median=statistics.median(following),
                chosen_up=100 * sum(x > 0 for x in chosen) / len(chosen),
                next_up=100 * sum(x > 0 for x in following) / len(following))


def coin_flips(results, trades, cut, cost):
    """As many strategies of pure chance, each trade a coin's worth of the real trades' swing."""
    rng = random.Random(COINS_SEED)
    swing = statistics.pstdev(spent(t, cost) for t in trades)
    before = sum(t.day < cut for t in trades)
    runs = []
    for _ in results:
        x = [rng.gauss(0, swing) for _ in trades]
        runs.append((sum(x[:before]), sum(x[before:])))
    runs.sort(reverse=True)
    return runs[0]


def add_months(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def walk_rounds(days, choose=12, trade=6):
    """(choose from, trade from, trade to) windows, each trading only days after it chose."""
    first, last = min(days), max(days)
    a = date(first.year, first.month, 1)
    rounds = []
    while add_months(a, choose) <= last:
        rounds.append((a, add_months(a, choose), add_months(a, choose + trade)))
        a = add_months(a, trade)
    return rounds


def walk_findings(results, days, cost):
    rows = []
    for a, b, c in walk_rounds(days):
        best = picked(results, a, b, cost)[0]
        rows.append(dict(start=b, end=min(c, max(days)), values=best[0], chosen=summary(between(best[1], a, b), cost)["total"],
                         next=summary(between(best[1], b, c), cost)["total"]))
    return rows


def neighbours(results, keys, values, cost):
    """The settings one step from these along one axis, and what each made."""
    table = tomllib.loads((HERE / "sweep.toml").read_text())
    if tuple(values) not in {r[0] for r in results}:
        return []
    near = []
    for g, r in results:
        moved = [i for i in range(len(keys)) if g[i] != values[i]]
        if len(moved) == 1:
            i = moved[0]
            axis = table[keys[i]]
            if abs(axis.index(g[i]) - axis.index(values[i])) == 1:
                near.append(summary(r, cost)["total"])
    return near


def current_values(s, keys):
    return tuple(s[k.split(".")[0]][k.split(".")[1]] for k in keys)


# --- printing --------------------------------------------------------------------------------------

def cents(x):
    return f"-${-x:,.2f}" if x < 0 else f"+${x:,.2f}"


def line_of(st):
    return (f"total {usd(st['total'])}   average {cents(st['average'])}"
            f"   won {st['won']:.1f}%   worst day {usd(st['worst'])}   worst fall ${st['fall']:,.0f}")


def show_run(symbol, days, trades, cost, skipped=0):
    order = sorted(days)
    st = summary(trades, cost)
    rules = Counter(t.rule for t in trades)
    print(f"{symbol} iron condor, {len(days)} days, {short(order[0])} - {short(order[-1])}"
          + (f", {cost * 100:g} cent a fill" if cost else ", no cost"))
    print(f"  traded {st['n']}   no trade {len(days) - skipped - st['n']}" + (f"   skipped {skipped}" if skipped else ""))
    print("  exits   " + "   ".join(f"{k} {rules[k]}" for k in ("take_profit", "touch", "stop", "close_by", "settled") if rules[k]))
    print("  " + line_of(st))


def show_costs(trades):
    print(f"{'a fill':>8} {'a condor':>9} {'total':>10} {'average':>9} {'won':>7}")
    for c in CENTS:
        st = summary(trades, c)
        print(f"{c * 100:>6.1f}c {usd(-c * 100 * FILLS_CLOSED) if c else '$0':>9} {usd(st['total']):>10} {cents(st['average']):>9} {st['won']:>6.1f}%")
    be = break_even(trades)
    print(f"it reaches zero at {be * 100:.2f} cents a fill" if be else "below zero before any cost at all")


def show_sweep(keys, results, days, trades, cost):
    cut = split_day(days)
    order = sorted(days)
    f = sweep_findings(results, cut, cost)
    flips = coin_flips(results, trades, cut, cost)
    print(f"{len(results):,} settings, chosen on {short(order[0])} - {short(cut - timedelta(days=1))}, judged on {short(cut)} - {short(order[-1])}")
    print(f"  the winner   {label(keys, f['best'])}")
    print(f"  chosen {usd(f['chosen'])}   next {usd(f['next'])}")
    print(f"  the top 20, next: {usd(f['top20'])}   the middle setting, next: {usd(f['median'])}")
    print(f"  settings that made money: {f['chosen_up']:.1f}% chosen, {f['next_up']:.1f}% next")
    print(f"  {len(results):,} coin flips, the best: {usd(flips[0])} chosen, {usd(flips[1])} next")


def show_walk(keys, rows, cost):
    print("choose on 12 months, trade the next 6" + (f", {cost * 100:g} cent a fill" if cost else ", no cost"))
    print(f"  {'traded':<20} {'chosen':>8} {'next':>8}")
    for r in rows:
        print(f"  {r['start']:%b %Y} - {r['end']:%b %Y}   {usd(r['chosen']):>8} {usd(r['next']):>8}")
        print(f"      the winner   {label(keys, r['values'])}")
    print(f"  what walking forward made: {usd(sum(r['next'] for r in rows))}")


def show_report(symbol, days, s, trades, cost, saved):
    keys, results = saved if saved else (None, None)
    cut = split_day(days)
    order = sorted(days)
    st = summary(trades, cost)
    print(f"BACKTEST REPORT   {symbol} iron condor   {short(order[0])} - {short(order[-1])}")
    gone = left_out(symbol)
    print(f"  days            {len(days)}: traded {st['n']}, no trade {len(days) - st['n']}, "
          + (f"{len(gone)} left out, no data" if gone else "none left out"))
    print(f"  settings tried  {len(results):,}" if results else "  settings tried  1 (no sweep saved for this symbol)")
    print(f"  no cost         {usd(summary(trades)['total'])}")
    print(f"  half a cent     {usd(summary(trades, 0.005)['total'])}")
    print(f"  one cent        {usd(summary(trades, 0.01)['total'])}")
    be = break_even(trades)
    print(f"  reaches zero    {be * 100:.2f} cents a fill" if be else "  reaches zero    before any cost")
    print(f"  first half      {usd(summary(between(trades, NEAR, cut), cost)['total'])}")
    print(f"  second half     {usd(summary(between(trades, cut, FAR), cost)['total'])}")
    print(f"  worst day       {usd(st['worst'])}   worst fall ${st['fall']:,.0f}")
    if results:
        near = neighbours(results, keys, current_values(s, keys), cost)
        if near:
            print(f"  neighbours      {len(near)} settings one step away: {usd(min(near))} to {usd(max(near))}")
        rows = walk_findings(results, days, cost)
        print(f"  walk forward    {len(rows)} rounds, {usd(sum(r['next'] for r in rows))}")
    print("  not tested      fills at the real spread (not in Alpaca's free data), fees, assignment, other markets")


# --- the commands ----------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("fetch", "run", "costs", "sweep", "walk", "report"))
    ap.add_argument("--symbol", default=None, help="underlying (default: condor.toml's)")
    ap.add_argument("--cost", type=float, default=0.0, metavar="DOLLARS", help="cost on each leg, each way")
    ap.add_argument("--skip-wide", metavar="close|HH:MM", help="skip wide days, judged up to this time")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="change a setting for this run")
    ap.add_argument("--until", metavar="YYYY-MM-DD", help="fetch up to this day (default: yesterday)")
    ap.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1), help="processes for a sweep")
    a = ap.parse_args(argv)
    s = condor.settings(changes=a.set)
    symbol = a.symbol or s["underlying"]
    s["underlying"] = symbol
    if a.command == "fetch":
        return fetch(symbol, a.until)
    days = load(symbol)
    if a.command == "sweep":
        keys, combos = grid()
        print(f"{len(combos):,} settings over {len(days)} days", flush=True)
        results = sweep(symbol, days, s, keys, combos, a.workers)
        with (CACHE / f"{symbol}.sweep").open("wb") as f:
            pickle.dump((keys, results), f, protocol=5)
        return show_sweep(keys, results, days, run_all(symbol, days, s), a.cost)
    if a.command == "walk":
        saved = saved_sweep(symbol)
        if not saved:
            raise SystemExit(f"no sweep saved for {symbol}: run  uv run backtest.py sweep --symbol {symbol}")
        return show_walk(saved[0], walk_findings(saved[1], days, a.cost), a.cost)
    skip = wide_days(days, a.skip_wide) if a.skip_wide else frozenset()
    trades = run_all(symbol, days, s, skip)
    if a.command == "run":
        return show_run(symbol, days, trades, a.cost, len(skip))
    if a.command == "costs":
        return show_costs(trades)
    show_report(symbol, days, s, trades, a.cost, saved_sweep(symbol))


if __name__ == "__main__":
    sys.exit(main())
