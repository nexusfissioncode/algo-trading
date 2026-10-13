# tradingview-mcp

Claude Code with TradingView's own MCP server: symbols, price history, the screener, technical
ratings, fundamentals, filings, calendars, news, watchlists and alerts. Then one paper order
through Alpaca's MCP server, decided from what TradingView shows.

## Connect TradingView

You need a TradingView plan that includes MCP access (Essential or higher; not a trial) and
Claude Code (https://claude.com/claude-code).

```
claude --version
claude mcp add --transport http tradingview https://mcp.tradingview.com/mcp
claude mcp list
claude
```

Inside Claude Code: `/mcp`, choose `tradingview`, then Authenticate, and sign in to TradingView
in your browser. If the sign-in page is blocked in one browser, copy the link Claude Code prints
and open it in a browser where you are already signed in to TradingView.

The tools are named `mcp-tv-...` and `mcp-watchlist-...` (for example `mcp-tv-get-ohlcv`), so a
permission rule uses the full name: `mcp__tradingview__mcp-tv-get-ohlcv`.

## Prompts to try

- "Find Apple's TradingView symbol."
- "Show me Bitcoin's last seven daily bars from Coinbase."
- "Which US common stocks over a hundred billion dollars have RSI under thirty five today?"
- "Give me TradingView's technical rating for the top three."
- "Revenue, net income and analyst targets for the first one."
- "Summarise its latest earnings call."
- "What earnings and economic events are coming up in the next seven days?"
- "Latest headlines for it, and summarise the top story."
- "Make a watchlist called MCP demo with those three."
- "Set a price alert on Bitcoin a little above the current price."
- "Did any of my alerts fire in the last hour?"

## What it cannot do (beta)

It cannot read the indicators or Pine Script on your chart, create webhook alerts, create
indicator or multi-condition alerts, or place orders. For orders, add a broker's MCP server.

## The lock: .claude/settings.json

Copy `.claude/settings.json` into the folder you start Claude Code from.

- `allow`: every TradingView tool, and Alpaca's read tools, run without asking.
- `ask`: anything that changes your TradingView account (alerts, watchlists), and a crypto order
  on Alpaca, asks you first, every time.
- `deny`: stock and option orders, closing everything and cancelling everything can never run
  from this folder. Deny beats ask, and ask beats allow.

## Add Alpaca (paper)

Your paper keys stay in environment variables; the settings file stores only their names.

```
export ALPACA_API_KEY=...       # from the paper dashboard
export ALPACA_SECRET_KEY=...
claude mcp add alpaca --scope project -e 'ALPACA_API_KEY=${ALPACA_API_KEY}' -e 'ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}' -e ALPACA_PAPER_TRADE=true -- uvx alpaca-mcp-server
```

## The strategy file

`strategy.md` is the plan Claude follows when an alert fires: read the alert history, check
TradingView's rating, the last bars and the news, and buy one hundred dollars of Bitcoin on
paper only if every check passes.

```
Read strategy.md and follow it. Read my TradingView alert history; if my Bitcoin alert fired,
check the rating, the bars and the news against the rules, and act on my Alpaca paper account.
```
