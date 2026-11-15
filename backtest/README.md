# backtest: an options strategy tested without flattering it

Plain Python on Alpaca's free market data. It runs the iron condor bot's own code (`condor.py`,
`strikes.py`, `exits.py`, `closer.py`, `market.py`, `broker.py`, copied unchanged apart from one
fix below) over every trading day Alpaca has option history for, since February 2024, and prints a
report that:

- **never peeks**: a decision only sees bars that had finished by that moment (a test proves it);
- **never drops a day**: days with no trade and condors still open at the close are counted, and a
  day with no data at all is named in the report;
- **shows a range of costs**, and the cost a fill at which the result reaches zero;
- **says how many settings were tried** beside the result;
- **keeps choosing apart from judging**: walk-forward picks a setting on twelve months, trades it on
  the six after, and moves on.

Nothing here places an order. The settings in `condor.toml` are placeholders to learn with, not
advice, and `sweep.toml` lists the values a sweep tries.

```
uv sync
export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...    # paper keys; they only read market data here

uv run backtest.py fetch                    # every day's one-minute bars, saved in .cache/ (a while)
uv run backtest.py run                      # condor.toml's settings, every day, no cost
uv run backtest.py run --cost 0.005         # half a cent on each leg, each way
uv run backtest.py run --skip-wide 10:00    # skip wide days, judged only by what is known at 10:00
uv run backtest.py costs                    # the same run at a range of costs
uv run backtest.py sweep                    # every combination in sweep.toml (slow; --workers)
uv run backtest.py walk                     # choose on 12 months, trade the next 6, again and again
uv run backtest.py report                   # all of it on one screen
uv run backtest.py report --set exits.touch=false   # change one setting for this run
uv run backtest.py fetch --symbol QQQ && uv run backtest.py report --symbol QQQ
uv run pytest -v
```

## What the report cannot tell you

- **Real fills.** Alpaca's free data has one-minute bars and trades for options, but no past bids
  and asks, so the true cost of a fill on a past day cannot be looked up. That is why the report
  shows a range of costs. Providers that sell past option quotes include Databento, ThetaData and
  Cboe's DataShop; this code uses none of them.
- **Paper fills** are simulated by the broker from live quotes: they test the code, not the cost.
- **One market, a short history.** Alpaca's option history starts in February 2024.
- **A look every sixty seconds** in a replay; the live bot looks every few seconds.
- **Flat costs**: real spreads are widest when stops fire. Fees and early assignment are left out.

## The fix in market.py

A one-minute bar is stamped with the minute it starts, so the bar stamped 10:00 is only finished at
10:01. `Replay._at` now takes the last bar that had finished by the clock:

```python
i = bisect_right(rows[0], t.timestamp() - BAR)      # only bars that have finished by t
```

`tests/test_no_peeking.py` fails without it.

## The free stock feed has holes

Alpaca's free IEX feed has days with few or no stock bars. `broker.py`
takes the whole market's feed for a day with fewer than 100 bars instead of losing it.
