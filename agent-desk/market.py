"""What the desk can look at: prices, an indicator, the news and the account.
Plain Python on Alpaca's API - the agents get these as tools. Paper account only."""
import os
from datetime import datetime, timedelta, timezone


def rsi_of(closes, period=14):
    """Wilder's RSI: average gain against average loss, on a scale of 0 to 100."""
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(c, 0) for c in changes[:period]) / period
    loss = sum(max(-c, 0) for c in changes[:period]) / period
    for c in changes[period:]:
        gain = (gain * (period - 1) + max(c, 0)) / period
        loss = (loss * (period - 1) + max(-c, 0)) / period
    return 100.0 if loss == 0 else round(100 - 100 / (1 + gain / loss), 1)


def summarize(symbol, closes):
    """The last price, the move over a day of hourly closes, and the RSI."""
    day = closes[-25:]
    return {"symbol": symbol, "price": round(closes[-1], 2),
            "change_24h_pct": round((day[-1] / day[0] - 1) * 100, 2),
            "high_24h": round(max(day), 2), "low_24h": round(min(day), 2),
            "rsi_14h": rsi_of(closes)}


def snapshot(symbol):
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    start = datetime.now(timezone.utc) - timedelta(hours=100)
    bars = CryptoHistoricalDataClient().get_crypto_bars(
        CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Hour, start=start))
    return summarize(symbol, [b.close for b in bars.data[symbol]])


def news(symbol, hours=24, limit=8):
    """The latest headlines that mention the coin."""
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    client = NewsClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    start = datetime.now(timezone.utc) - timedelta(hours=hours)
    found = client.get_news(NewsRequest(symbols=symbol.replace("/", ""), start=start, limit=limit))
    return [{"time": n.created_at.strftime("%H:%M UTC"), "headline": n.headline}
            for n in found.data["news"]]


def trading():
    from alpaca.trading.client import TradingClient
    return TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)


def account(symbol):
    """What the risk manager needs: the money, today's result, and whether we already hold it."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    client = trading()
    a = client.get_account()
    held = [p for p in client.get_all_positions() if p.symbol == symbol.replace("/", "")]
    pending = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
    return {"cash": round(float(a.cash), 2), "equity": round(float(a.equity), 2),
            "today_pnl": round(float(a.equity) - float(a.last_equity), 2),
            "holding": {"qty": held[0].qty, "value": round(float(held[0].market_value), 2)}
            if held else None,
            "open_orders": len(pending)}
