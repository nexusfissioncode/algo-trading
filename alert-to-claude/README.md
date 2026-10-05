# alert-to-claude

Every command from the video, as in its description.

```text
COPY AND PASTE: everything from the video

Install (macOS)
Claude Code:
curl -fsSL https://claude.ai/install.sh | bash
uv (runs the Alpaca MCP server):
curl -LsSf https://astral.sh/uv/install.sh | sh
cloudflared (Intel Mac; on Apple silicon use cloudflared-darwin-arm64.tgz, or: brew install cloudflared):
curl -sLO https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz && tar -xzf cloudflared-darwin-amd64.tgz

.mcp.json (the keys stay in environment variables, never in the file)
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "${ALPACA_API_KEY}",
        "ALPACA_SECRET_KEY": "${ALPACA_SECRET_KEY}",
        "ALPACA_PAPER_TRADE": "true"
      }
    }
  }
}

rules.md
- Only trade BTC/USD. An alert for anything else: skip it.
- Check the live price. If the alert's price is more than 3% away, it is stale: skip it.
- A buy alert: if the account already holds BTC/USD, skip it - never double up. Otherwise buy 1000 dollars of BTC/USD with a market order.
- A sell alert: if the account holds BTC/USD, close the whole position. Otherwise skip it.
- Never print account numbers or ids.
- Finish with exactly one line: DECISION: BOUGHT, SOLD or SKIPPED - and why, in under twelve words.

How the receiver starts Claude (headless)
claude -p "THE ALERT" --mcp-config .mcp.json --strict-mcp-config --tools "" --allowedTools mcp__alpaca__get_account_info,mcp__alpaca__get_all_positions,mcp__alpaca__get_orders,mcp__alpaca__get_crypto_latest_quote,mcp__alpaca__get_crypto_latest_trade,mcp__alpaca__get_crypto_snapshot,mcp__alpaca__place_crypto_order,mcp__alpaca__close_position --permission-mode dontAsk --append-system-prompt "THE RULES" --output-format stream-json --verbose

Run it (terminal one: the receiver)
export ALPACA_API_KEY=your-paper-key-id
export ALPACA_SECRET_KEY=your-paper-secret
export ALERT_SECRET=pick-a-word
python3 receiver.py

Terminal two: the tunnel (zsh; prints only your public address)
./cloudflared tunnel --url http://localhost:8765 |& grep -o 'https://.*trycloudflare.com'

Terminal three: send a test alert
curl -s -X POST https://YOUR-WORDS.trycloudflare.com/alert -d '{"secret":"pick-a-word","ticker":"BTCUSD","action":"buy","price":84000}'

TradingView alert
Webhook URL: https://YOUR-WORDS.trycloudflare.com/alert
Message:
{"secret":"pick-a-word","ticker":"{{ticker}}","action":"{{strategy.order.action}}","price":{{close}}}

Paper trading only. Nothing in this video is financial advice.
```
