# guardrail-mcp

Every command from the video, as in its description.

```text
Every command from the video, in order. Paper trading only; education, not financial advice.

EARLIER IN THE SERIES
Claude and Alpaca, by chat: https://youtu.be/EYmt8iX31ao
An alert wakes Claude: https://youtu.be/SED4Wyf82l0
Always on, for free: https://youtu.be/K26jC0z6n2w

SETUP
Claude Code: https://code.claude.com/docs/en/setup
curl -fsSL https://claude.ai/install.sh | bash   (then run: claude, and sign in)
uv: https://docs.astral.sh/uv/
claude --version
uv --version
Alpaca paper keys: dashboard, API Keys, Generate (the secret is shown once). Keep them in a file:
echo 'export ALPACA_API_KEY="your key id"' | tee trading.env
echo 'export ALPACA_SECRET_KEY="your secret"' | tee -a trading.env
chmod 600 trading.env && source trading.env
env | grep ALPACA | sed 's/=.*/=(set)/'
claude mcp add alpaca --scope project -e 'ALPACA_API_KEY=${ALPACA_API_KEY}' -e 'ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}' -e ALPACA_PAPER_TRADE=true -- uvx alpaca-mcp-server
claude mcp list

CLAUDE.md (the rules, in words)
- Only trade BTC/USD or ETH/USD.
- Never spend more than 1000 dollars on one order.
- Never double up: do not buy a coin the account already holds.
- If the account is down 200 dollars or more today, do not buy anything until tomorrow.

server.py (the parts that matter)
# /// script
# dependencies = ["mcp", "alpaca-py"]
# ///
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("guard")

@mcp.tool()
def rsi(symbol: str = "BTC/USD"):
    """The 14-hour RSI of a coin. Use this tool for RSI; do not work it out yourself."""
    prices = closes(symbol)      # 100 hourly bars from Alpaca
    return {"symbol": symbol, "rsi": rsi_of(prices), "last_close": prices[-1]}

@mcp.tool()
def place_order(symbol: str, side: str, dollars: float = 0):
    """Buy a coin for dollars, or sell the whole position - only if your rules allow it.
    The only way to place an order."""
    # read the account, the positions and the open orders, then:
    broken = check(symbol, side, dollars, held or pending, today_pnl)
    if broken:
        return {"placed": False, "refused_because": broken}
    # ...submit a market order with TradingClient(key, secret, paper=True)

mcp.run()

rules.json
{"symbols": ["BTC/USD", "ETH/USD"], "max_dollars_per_order": 1000,
 "never_double_up": true, "max_loss_per_day": 200}

TRY IT WITHOUT CLAUDE
uv run server.py --check
npx @modelcontextprotocol/inspector uv run server.py

RULES IN WORDS vs RULES IN CODE
To test the code on its own: mv CLAUDE.md CLAUDE.md.off (and back afterwards)

GIVE IT TO CLAUDE
claude mcp add guard --scope project -e 'ALPACA_API_KEY=${ALPACA_API_KEY}' -e 'ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}' -- uv run server.py
claude
Ctrl+O shows each tool call and its answer.

.claude/settings.json (the lock)
{"permissions": {
  "defaultMode": "default",
  "allow": ["mcp__guard__rsi", "mcp__alpaca__get_account_info", "mcp__alpaca__get_all_positions",
            "mcp__alpaca__get_orders", "mcp__alpaca__get_crypto_latest_quote",
            "mcp__alpaca__get_crypto_snapshot", "mcp__alpaca__get_crypto_bars"],
  "deny": ["mcp__alpaca__place_crypto_order", "mcp__alpaca__place_stock_order",
           "mcp__alpaca__place_option_order", "mcp__alpaca__close_position",
           "mcp__alpaca__close_all_positions", "mcp__alpaca__replace_order_by_id"]}}

THE BOT FROM VIDEO TWO, GUARDED
In receiver.py, the allowed tools: replace mcp__alpaca__place_crypto_order and
mcp__alpaca__close_position with mcp__guard__rsi and mcp__guard__place_order.
In the bot's .mcp.json, add the guard beside alpaca:
"guard": {"command": "uv", "args": ["run", "../server.py"],
          "env": {"ALPACA_API_KEY": "${ALPACA_API_KEY}", "ALPACA_SECRET_KEY": "${ALPACA_SECRET_KEY}"}}
Run it and send a test alert:
export ALERT_SECRET=pick-a-long-secret
python3 receiver.py
curl -s -X POST localhost:8765/alert -d '{"secret": "pick-a-long-secret", "ticker": "BTCUSD", "action": "buy", "price": 84000}'
On the server from video three: copy server.py and rules.json next to the bot, then
sudo systemctl restart alert-bot
```
