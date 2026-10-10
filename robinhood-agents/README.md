# robinhood-agents

Claude Code trading through Robinhood's own MCP server, with your own allow and deny list.

## Connect

You need a Robinhood individual account in good standing, and a desktop browser to sign in.

```
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
claude
```

Inside Claude Code: `/mcp`, choose `robinhood-trading`, then Authenticate. Robinhood opens a
sign-in page and then the setup of a separate Agentic account. The agent can only trade in that
account, with the money you move into it. It can read your other accounts.

## The lock you control: .claude/settings.json

Copy `.claude/settings.json` into the folder you start Claude Code from.

- `allow`: every Robinhood tool runs without asking - quotes, positions, previews...
- `ask`: ...except placing or cancelling a crypto order, which asks you first, every time.
- `deny`: stock orders, option orders and exercising options can never run from this folder,
  whatever anyone types. Deny beats ask, and ask beats allow.

Robinhood's own trade-approval switch is in the Robinhood app, not here. Keep it on until you
trust your setup.

Real money: Robinhood has no paper account. Start with a few dollars.
