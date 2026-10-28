# wheel-bot: the wheel, on your stocks or a screen

Plain Python on an Alpaca **paper** account. Each run reads the account and works out where every
stock is on the wheel:

1. **Nothing held** - the picker names stocks, each one's put nearest the target delta is found, and
   they are ranked by what the put pays for the cash it sets aside (over a year, since expiries
   differ). The best gets a **cash-secured put**.
2. **A short put open** - bought back at half its premium, rolled with three weeks or less to go,
   or left to run. If it expires worthless, the stock is free for a new put.
3. **Shares held** (assigned, at the strike) - a **covered call** at or above what they cost.
4. **A short call open** - managed the same way. If the shares are called away, back to step 1.

The bot keeps no state of its own: the account is the state. Every setting is in `wheel.toml`, and
every number in it is a placeholder to learn with, not advice.

```
uv sync
export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...           # paper keys
export SEC_USER_AGENT="Your Name your-email@example.com"   # or set it in wheel.toml

uv run wheel.py                    # a dry run: what it would do, and why
uv run wheel.py --picker list      # pick from your own list instead of the screen
uv run wheel.py --trade            # the same, and place the orders
uv run wheel.py --no-new           # only look after what is already in the wheel
uv run wheel.py --set filters.rsi.below=40   # change one setting for one run
uv run pytest -v                   # every turn of the wheel, on made-up positions
```

## Picking stocks

`picker = "list"` uses `[list] symbols` as written. `picker = "screen"` starts from every US stock
with options on Alpaca and runs the filters in `[screen] filters`, in order:

| Filter | Keeps | Settings |
|---|---|---|
| `market_cap` | companies worth at least `min_dollars` | shares from the SEC, times the last price |
| `rsi` | stocks with RSI on daily closes under `below` ("oversold") | `days`, `below` |
| `above_200` | stocks above their `days`-day average | `days` |

**Your own filter** is one file in `filters/` with one function, then its name in the list:

```python
def apply(symbols, market, settings):        # -> the symbols it keeps
    closes = market.closes(symbols, settings["days"])
    return [s for s in symbols if ...]
```

`market` answers `prices`, `closes` and `market_caps`, each fetched once per run; `settings` is
`[filters.<your file>]` in `wheel.toml`. **Your own picker** is one file in `pickers/` with
`pick(market, settings, say)` returning symbols; name it in `picker = "..."` or `--picker`.

## Where the numbers come from

- **Option prices and delta**: Alpaca's free `indicative` options feed - derived from the official
  feed, not the official quotes. Contracts about a month out carry delta; same-day ones do not.
- **Open interest**: Alpaca's contract list.
- **Stock prices and closes**: Alpaca's free IEX feed.
- **Shares, for market cap**: the SEC's XBRL frames - the cover-page count, or for companies with
  two share classes (Alphabet, Meta) the quarter's weighted average. Foreign companies report their
  own shares, not the ADRs that trade here, so `us_only = true` leaves them out. A company with
  share classes at very different prices (Berkshire Hathaway) can come out wrong or missing: the run
  prints the market cap it used. The SEC asks every caller to send a User-Agent naming who runs it.

## Running it every day

`run-wheel.sh` is what a scheduler runs: it reads the keys from `keys.env` (yours, `chmod 600`,
never committed) and adds each run's output to `runs.log`. `schedule.cron` has one line for
`crontab -e`. On a laptop it only runs while the laptop is awake; the `always-on-cloud` and
`scheduled-agents` folders show the same kind of job on an always-on server.

## Practising the call side

`uv run buy_shares.py BAC 100` buys a hundred shares at the market: what an assignment would leave
in the account (there, at the strike). The next run sells the covered call.

Each order starts at the mid price. If it has not filled after `walk_seconds`, the bot asks a little
less (or pays a little more), `walk_steps` times, until it reaches the bid (or the ask), then up to `walk_past` steps beyond it: the free
"indicative" option quotes are close to the market the broker fills against, not the same - the
`[orders]` table in wheel.toml.

Options orders are day orders with no extended hours: run it while the market is open (09:30-16:00
New York). Paper trading only; nothing here is financial advice.
