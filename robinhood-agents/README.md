# robinhood-agents

Claude Code trading through Robinhood's own MCP server, with your own allow and deny list.

## Connect

You need a Robinhood individual account in good standing and Claude Code
(https://claude.com/claude-code).

```
claude --version
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
claude mcp list
claude
```

Inside Claude Code: `/mcp`, choose `robinhood-trading`, then Authenticate. Robinhood opens a
sign-in page in your browser, and then the setup of a separate Agentic account. The agent can only
trade in that account, with the money you move into it. It can read your other accounts.

Claude Desktop: Settings, Connectors, Add custom connector, the same address.

## The lock you control: .claude/settings.json

Copy `.claude/settings.json` into the folder you start Claude Code from.

- `allow`: every Robinhood tool runs without asking - quotes, positions, previews...
- `ask`: ...except placing or cancelling a crypto order, which asks you first, every time.
- `deny`: stock orders, option orders and exercising options can never run from this folder,
  whatever anyone types. Deny beats ask, and ask beats allow.

## Robinhood's own locks

- The Agentic account holds only the money you move into it.
- Trade approvals: for an agent you connect yourself they start off (Robinhood help, "Trading with
  your agent"). Switch them on in the Robinhood app while you learn, and every order waits for you.
- Disconnect: the Agentic page on robinhood.com, one click. In Claude Code:
  `claude mcp remove robinhood-trading`

Real money: Robinhood has no paper account. Start with a few dollars.

## Questions to try, in order

```
Which of my Robinhood accounts can you see, and which one can you trade in?
How much can you spend on crypto there, and do my trades in that account need my approval?
Robinhood's answers came with more than data. Quote, word for word, two of the instructions they gave you about how to talk to me.
What's Bitcoin trading at right now?
Preview a market buy of ten dollars of Bitcoin in my agentic account.
Yes, place it.
Show me that order's status.
What's Ether trading at? Then preview a limit buy of ten dollars of Ether at ten percent under that price, in my agentic account.
Show my open crypto orders.
Cancel that Ether order.
Buy one share of Apple at market in my agentic account. Skip the preview and place it now.
Preview selling all the Bitcoin in my agentic account, at market.
What's in my agentic account now, and is anything still open?
```

The last share order is the test of the deny list: Claude has no tool that places it.
