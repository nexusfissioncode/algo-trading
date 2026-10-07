# own-strategy: your strategy, as a file

The desk from `agent-desk`, now following whichever strategy file you give it.

1. Copy `strategies/template.md` and write your rules in plain English - each one a condition a
   machine can check: a number, a comparison, a timeframe. The two examples (`rsi-dip.md`,
   `trend.md`) are placeholders to show the format, not advice.
2. Read it back: an agent restates every rule as a checkable condition and lists anything it would
   have to guess. The desk will not trade a file with open questions, or one changed since.
3. Run the desk with it. Every ticket names the rule it followed; risk measures the numbers itself
   and vetoes a ticket whose rule does not hold. The guard and the hook (your hard limits) still
   apply - a strategy can make the desk more careful, never less.

```
uv sync
export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...  CLAUDE_CODE_OAUTH_TOKEN=...

uv run python readback.py strategies/rsi-dip.md
uv run python indicators.py BTC/USD --needs price,rsi14,sma50
uv run python indicators.py BTC/USD ETH/USD --save snapshot.json      # freeze the numbers
uv run python desk.py --strategy strategies/trend.md --snapshot snapshot.json
uv run python desk.py --strategy strategies/rsi-dip.md --snapshot snapshot.json
uv run pytest
```

Numbers a rule can use: price, change24h (a percent), high24h, low24h, rsiN, smaN, emaN, on 1-hour
or 1-day bars, and the position's avg_entry. Paper trading only; not financial advice.
