# Algo trading

Code for automated trading with AI agents: one folder per project, each one complete on its own,
and every folder's own README lists the commands, in order.

| Folder | What it is |
|---|---|
| [`alert-to-claude/`](alert-to-claude) | A TradingView alert wakes Claude Code, which checks the setup through the Alpaca MCP server and places the order - or explains why not. |
| [`always-on-cloud/`](always-on-cloud) | The same bot on a free Google Cloud e2-micro, always on: systemd, Caddy, keys on the server. |
| [`guardrail-mcp/`](guardrail-mcp) | Your own MCP server: an RSI tool, and an order tool that checks your rules in code before anything reaches the broker. |
| [`scheduled-agents/`](scheduled-agents) | Two Claude Code skills - a morning brief and a trade journal - run by cron, read-only, with nobody at the keyboard. |
| [`agent-desk/`](agent-desk) | A desk of three agents on the Claude Agent SDK - an analyst, a risk manager and a trader - that check each other before an order goes anywhere. |
| [`own-strategy/`](own-strategy) | Your strategy in one plain-English file: the desk reads it back before it may trade, follows it, and names the rule behind every ticket. Template in `strategies/`. |
| [`robinhood-agents/`](robinhood-agents) | Claude Code on Robinhood's own MCP server, trading only in the separate agentic account: the connect command and a settings file that asks before every crypto order and denies stock and option orders. |

## Before you run anything

- **Paper trading only.** Every folder is set up for an Alpaca *paper* account. Nothing here is
  financial advice; it is code to learn from.
- **Keys stay in your environment**, never in a file you commit: `ALPACA_API_KEY` and
  `ALPACA_SECRET_KEY` from the Alpaca dashboard (paper), and for Claude either your Claude Code
  sign-in or `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`. If you share or sell what you
  build, sign it in with an API key from the Anthropic console instead.
- Python projects use [uv](https://docs.astral.sh/uv/).

## Licence

MIT - see [LICENSE](LICENSE).
