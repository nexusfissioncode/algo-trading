"""The guard from guardrail-mcp: your rules, in code. The only way an order reaches the
broker, and it checks every rule first - whatever any agent was told."""
import json
from pathlib import Path

import market

RULES = json.loads((Path(__file__).parent / "rules.json").read_text())


def check(symbol, side, dollars, holding, today_pnl, rules=RULES):
    """Every rule this order breaks, in plain words. Empty means it may go."""
    broken = []
    if symbol not in rules["symbols"]:
        broken.append(f"{symbol} is not on the list: {', '.join(rules['symbols'])}")
    if side == "buy":
        if dollars > rules["max_dollars_per_order"]:
            limit = rules["max_dollars_per_order"]
            broken.append(f"{dollars:g} dollars is over the limit of {limit}")
        if rules["never_double_up"] and holding:
            broken.append(f"already holding or buying {symbol} - never double up")
        if today_pnl <= -rules["max_loss_per_day"]:
            broken.append(f"down {-today_pnl:.0f} dollars today - no more buys until tomorrow")
    return broken


def place(symbol, side, dollars):
    """Buy for a number of dollars, or sell the whole position - if the rules allow it."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
    acct = market.account(symbol)
    holding = bool(acct["holding"] or acct["open_orders"])
    broken = check(symbol, side, dollars, holding, acct["today_pnl"])
    if broken:
        return {"placed": False, "refused_because": broken}
    client = market.trading()
    if side == "sell":
        client.close_position(symbol.replace("/", ""))
        return {"placed": True, "sold": symbol}
    order = client.submit_order(MarketOrderRequest(
        symbol=symbol, notional=dollars, side=OrderSide.BUY, time_in_force=TimeInForce.GTC))
    return {"placed": True, "bought": symbol, "dollars": dollars, "status": str(order.status.value)}
