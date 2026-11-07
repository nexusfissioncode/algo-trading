# iron-condor-bot: a same-day iron condor, with exits that work

Plain Python on an Alpaca **paper** account. Once a day, on SPY options that expire that same day
(0DTE):

1. **Where the strikes go** - at the entry time it prices the at-the-money straddle (the call plus
   the put at the strike nearest the price). 85% of that is the expected move. The short put and
   short call sit about that far either side of the price; each wing is `wing` dollars further out.
   Alpaca's free options data has no delta for same-day options, so the strikes come from prices.
2. **Opening it** - all four legs in one order, at the mid. If it does not fill, it asks once more,
   halfway to the natural price (never under `least_credit`), then gives up for the day.
3. **Watching it** - every few seconds: what buying it back costs, and the profit or loss.
4. **Getting out** - the first of four rules that fires closes it:

| Rule | Fires when | Setting |
|---|---|---|
| `take_profit` | buying it back costs half the credit or less | `take_profit = 0.50` |
| `stop` | buying it back costs twice the credit or more | `stop = 2.0` |
| `touch` | SPY reaches a short strike | `touch = true` |
| `close_by` | it is 15:15 New York, whatever happens | `close_by = "15:15"` |

The broker holds no stop for you: Alpaca's options orders are market or limit only, so the rules
live in this program, and it has to be running to use them. A stop limits a loss, it does not
prevent one: in a fast market the buy-back fills past the stop.

The buy-back is one four-leg order too. It starts at the mid; if nobody takes it, every
`walk_seconds` it reads the quotes again and asks a little more, `walk_steps` times up to the
natural price (shorts at the ask, wings at the bid), then `walk_past` steps beyond it.

The bot keeps no notes of its own: if it stops and starts again, it finds today's condor in the
account's positions and carries on watching. Every setting is in `condor.toml`, and every number in
it is a placeholder to learn with, not advice.

```
uv sync
export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...    # paper keys

uv run condor.py                       # today's condor: price, straddle, strikes, credit - a dry run
uv run condor.py --trade               # open it at 10:00 New York, watch it, close it by the rules
uv run condor.py --close-now           # close today's open condor now
uv run condor.py --replay 2026-10-23   # a past day on its real prices; nothing is sent
uv run condor.py --replay 2026-10-07 --set exits.touch=false   # change a setting for one run
uv run pytest -v                       # every rule, on made-up prices
```

## Replaying a past day

`--replay` fetches that day's one-minute bars for SPY and its same-day options (strikes within 5%
of the open) and keeps them in `.cache/`. The bot runs exactly as it would live, looking once a
minute, and every order "fills" at the price it asks. Bars are trades, not quotes, so a replayed
fill is an estimate; a real fill is usually worse.

## Where the numbers come from

- **SPY's price**: Alpaca's free IEX feed.
- **Option quotes**: Alpaca's free `indicative` options feed - derived from the official feed, not
  the official quotes. The paper broker fills against the real market, so a price that looks fair
  here can sit unfilled: that is what the walk is for.
- **Past days**: Alpaca's one-minute bars, kept for expired contracts too.

## Things to know before you run it

- **Times**: on expiry day Alpaca refuses orders for SPY options after 15:30 New York and sells
  out expiring positions from 15:45. `close_by` sits before both.
- **SPY options can be assigned early** and settle in shares; closing before the bell avoids it.
  Index options (XSP, SPX) settle in cash and cannot be assigned early, but Alpaca's market data
  has no index prices yet, so this bot trades SPY.
- **The most it can lose** is the wing width less the credit, times a hundred, per contract - the
  run prints it in dollars before anything is sent.
- **Market hours**: options orders are day orders with no extended hours. Run it while the market
  is open (09:30-16:00 New York).

Paper trading only; nothing here is financial advice.
