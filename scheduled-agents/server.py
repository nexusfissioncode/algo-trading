# /// script
# dependencies = ["mcp>=2.2", "alpaca-py"]
# ///
"""guard: your own MCP server. Two tools for Claude - an indicator, and an order tool
that checks your rules in code before anything reaches the broker. Paper account only."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp.server.mcpserver import MCPServer

RULES = json.loads((Path(__file__).parent / "rules.json").read_text())
mcp = MCPServer("guard")


def rsi_of(closes, period=14):
    """Wilder's RSI: average gain against average loss, on a scale of 0 to 100."""
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(c, 0) for c in changes[:period]) / period
    loss = sum(max(-c, 0) for c in changes[:period]) / period
    for c in changes[period:]:
        gain = (gain * (period - 1) + max(c, 0)) / period
        loss = (loss * (period - 1) + max(-c, 0)) / period
    return 100.0 if loss == 0 else round(100 - 100 / (1 + gain / loss), 1)


def closes(symbol, hours=100):
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    start = datetime.now(timezone.utc) - timedelta(hours=hours)
    bars = CryptoHistoricalDataClient().get_crypto_bars(
        CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Hour, start=start))
    return [b.close for b in bars.data[symbol]]


@mcp.tool()
def rsi(symbol: str = "BTC/USD") -> dict:
    """The 14-hour RSI of a coin, from Alpaca's hourly bars. Above 70 is often read as
    overbought, below 30 as oversold. Use this tool for RSI; do not work it out yourself."""
    prices = closes(symbol)
    return {"symbol": symbol, "rsi": rsi_of(prices), "last_close": prices[-1]}


def check(symbol, side, dollars, holding, today_pnl):
    """Every rule this order breaks, in plain words. Empty means it may go."""
    broken = []
    if symbol not in RULES["symbols"]:
        broken.append(f"{symbol} is not on the list: {', '.join(RULES['symbols'])}")
    if side == "buy":
        if dollars > RULES["max_dollars_per_order"]:
            limit = RULES["max_dollars_per_order"]
            broken.append(f"{dollars:g} dollars is over the limit of {limit}")
        if RULES["never_double_up"] and holding:
            broken.append(f"already holding or buying {symbol} - never double up")
        if today_pnl <= -RULES["max_loss_per_day"]:
            broken.append(f"down {-today_pnl:.0f} dollars today - no more buys until tomorrow")
    return broken


def trading():
    from alpaca.trading.client import TradingClient
    return TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)


@mcp.tool()
def place_order(symbol: str, side: str, dollars: float = 0) -> dict:
    """Buy a coin for a number of dollars, or sell (close) the whole position - in the paper
    account, and only if your rules allow it. The only way to place an order."""
    from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest
    client = trading()
    account = client.get_account()
    held = any(p.symbol == symbol.replace("/", "") for p in client.get_all_positions())
    # an order not filled yet counts too, or two quick buys would both get through
    pending = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
    today_pnl = float(account.equity) - float(account.last_equity)
    broken = check(symbol, side, dollars, held or bool(pending), today_pnl)
    if broken:
        return {"placed": False, "refused_because": broken}
    if side == "sell":
        client.close_position(symbol.replace("/", ""))
        return {"placed": True, "sold": symbol}
    order = client.submit_order(MarketOrderRequest(
        symbol=symbol, notional=dollars, side=OrderSide.BUY, time_in_force=TimeInForce.GTC))
    return {"placed": True, "bought": symbol, "dollars": dollars, "status": str(order.status.value)}


if __name__ == "__main__":
    if "--check" in sys.argv:     # a quick look without Claude: the tools, and one real answer
        print("guard: rules", json.dumps(RULES))
        print("guard: rsi", json.dumps(rsi("BTC/USD")))
    else:
        mcp.run()                 # speak MCP over stdin and stdout, until Claude hangs up
