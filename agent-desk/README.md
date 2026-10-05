# agent-desk: a desk of three agents

One AI that reads the market, decides and places the order is marking its own homework. This is
the same job split across a desk, on the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/):

| Seat | Job | Tools | Model |
|---|---|---|---|
| `analyst.py` | reads the price, the RSI and the news; writes one ticket | `snapshot`, `news` (read only) | Haiku |
| `risk.py` | checks the ticket against the account and your rules: approve, resize or veto | `account` (read only) | Sonnet |
| `trader.py` | places the order risk signed - that order and no other | `place_order` (the guard) | Haiku |
| `desk.py` | plain Python, not an AI: hands the ticket along, and a veto ends the run | - | - |

The order has three locks: only the trader has an order tool; that tool is the guard from the
`guardrail-mcp` folder (your rules in code, `rules.json`); and a hook in `trader.py` refuses any
call that differs from the signed order.

## Run it

```
uv sync
export ALPACA_API_KEY=...          # paper keys, from the Alpaca dashboard
export ALPACA_SECRET_KEY=...
export CLAUDE_CODE_OAUTH_TOKEN=... # from: claude setup-token (or use your Claude Code sign-in)

uv run python analyst.py BTC/USD               # one seat on its own: a ticket
uv run python risk.py ticket.json              # a verdict on a saved ticket
uv run python trader.py BTC/USD 250            # place a signed order of 250 dollars
uv run python trader.py BTC/USD 250 --ask 5000 # signed 250, told 5000: the hook refuses
uv run python desk.py                          # the whole desk, every coin in rules.json
uv run pytest                                  # the tests, with the agents and the broker faked
```

Every run is added to `desk-log.jsonl`. A desk run costs a few cents per coin on an API key.
Paper trading only; not financial advice.
