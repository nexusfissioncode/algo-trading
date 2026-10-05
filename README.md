# Algo trading, the code from Nexus Fission

The code from the [Nexus Fission](https://www.youtube.com/@nexusfission) videos on automated trading:
one folder per video, each one complete on its own. Every video builds it from nothing on screen,
and every folder's own README lists the commands.

| Folder | What it is | Video |
|---|---|---|
| [`alert-to-claude/`](alert-to-claude) | A TradingView alert wakes Claude Code, which checks the setup through the Alpaca MCP server and places the order - or explains why not. | [My AI trades while I'm away](https://youtu.be/SED4Wyf82l0) |
| [`always-on-cloud/`](always-on-cloud) | The same bot on a free Google Cloud e2-micro, always on: systemd, Caddy, keys on the server. | [My AI trading bot runs 24/7 on a free Google Cloud server](https://youtu.be/K26jC0z6n2w) |
| [`guardrail-mcp/`](guardrail-mcp) | Your own MCP server: an RSI tool, and an order tool that checks your rules in code before anything reaches the broker. | [I tried to talk my AI past my trading rules. Code stopped it.](https://youtu.be/b_npdVpQN9k) |
| [`scheduled-agents/`](scheduled-agents) | Two Claude Code skills - a morning brief and a trade journal - run by cron, read-only, with nobody at the keyboard. | [My AI agent writes my trading brief at 6:30am](https://youtu.be/XZ1VAnWPryQ) |
| [`agent-desk/`](agent-desk) | A desk of three agents on the Claude Agent SDK - an analyst, a risk manager and a trader - that check each other before an order goes anywhere. | coming next |

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
