"""The account, for the seats that need it. Paper account only."""
import os


def trading():
    from alpaca.trading.client import TradingClient
    return TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)


def account(symbol):
    """The money, today's result, and the position in a coin (with its average entry price)."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    client = trading()
    a = client.get_account()
    held = [p for p in client.get_all_positions() if p.symbol == symbol.replace("/", "")]
    pending = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
    position = None
    if held:
        p = held[0]
        position = {"qty": p.qty, "value": round(float(p.market_value), 2),
                    "avg_entry": round(float(p.avg_entry_price), 2)}
    return {"cash": round(float(a.cash), 2), "equity": round(float(a.equity), 2),
            "today_pnl": round(float(a.equity) - float(a.last_equity), 2),
            "position": position, "open_orders": len(pending)}
