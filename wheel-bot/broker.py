"""Everything that talks to Alpaca, in one place. Paper account only.

Keys come from the environment: ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys).
Answers are plain dicts (raw_data), so a new exchange code on Alpaca's side never breaks a run."""
import functools
import os
import time
from datetime import date, datetime, timedelta, timezone

from alpaca.data.enums import DataFeed, OptionsFeed
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import (OptionChainRequest, OptionLatestQuoteRequest, StockBarsRequest,
                                 StockSnapshotRequest)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (AssetClass, AssetStatus, OrderSide, OrderType, PositionIntent,
                                  QueryOrderStatus, TimeInForce)
from alpaca.trading.requests import (GetAssetsRequest, GetOptionContractsRequest, GetOrdersRequest,
                                     LimitOrderRequest, MarketOrderRequest, ReplaceOrderRequest)
from requests.exceptions import ConnectionError, Timeout


def retried(fn):
    """Try a read again after a dropped connection: a bot that runs on its own should not stop for
    one. Orders are never retried - a second try could place a second order."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except (ConnectionError, Timeout):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
    return run


def _keys():
    return os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]


def trading():
    return TradingClient(*_keys(), paper=True, raw_data=True)


def stocks():
    return StockHistoricalDataClient(*_keys(), raw_data=True)


def options():
    return OptionHistoricalDataClient(*_keys(), raw_data=True)


# --- the account ---------------------------------------------------------------------------------

@retried
def account():
    a = trading().get_account()
    return {"cash": float(a["cash"]), "options_buying_power": float(a["options_buying_power"]),
            "options_level": int(a.get("options_trading_level") or 0)}


@retried
def positions():
    return trading().get_all_positions()


@retried
def open_orders():
    return trading().get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True))


@retried
def market_open():
    return trading().get_clock()["is_open"]


# --- stocks --------------------------------------------------------------------------------------

@retried
def stocks_with_options():
    """Every active, tradable US stock on Alpaca that has options: [{symbol, name}]."""
    assets = trading().get_all_assets(GetAssetsRequest(
        status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY, attributes="has_options"))
    return [{"symbol": a["symbol"], "name": a["name"]} for a in assets if a["tradable"]]


@retried
def prices(symbols):
    """The last price of each stock (the free IEX feed)."""
    out = {}
    for i in range(0, len(symbols), 500):
        snaps = stocks().get_stock_snapshot(StockSnapshotRequest(
            symbol_or_symbols=symbols[i:i + 500], feed=DataFeed.IEX))
        for s, v in snaps.items():
            if v and v.get("latestTrade"):
                out[s] = v["latestTrade"]["p"]
            elif v and v.get("dailyBar"):
                out[s] = v["dailyBar"]["c"]
    return out


@retried
def closes(symbols, days):
    """Daily closes, oldest first, for about `days` trading days."""
    start = datetime.now(timezone.utc) - timedelta(days=int(days * 1.5) + 10)
    out = {s: [] for s in symbols}
    for i in range(0, len(symbols), 100):
        bars = stocks().get_stock_bars(StockBarsRequest(
            symbol_or_symbols=symbols[i:i + 100], timeframe=TimeFrame.Day, start=start,
            feed=DataFeed.IEX))
        for s, rows in bars.items():
            out[s] = [b["c"] for b in rows]
    return out


# --- options -------------------------------------------------------------------------------------

@retried
def option_contracts(stock, kind, today, min_days, max_days):
    """Every put or call of a stock in the days window, with greeks, quotes and open interest.
    Delta and the quotes come from the free indicative feed; open interest from the contract list."""
    lo, hi = (today + timedelta(days=min_days)).isoformat(), (today + timedelta(days=max_days)).isoformat()
    listed, token = {}, None
    while True:
        r = trading().get_option_contracts(GetOptionContractsRequest(
            underlying_symbols=[stock], type=kind, expiration_date_gte=lo, expiration_date_lte=hi,
            limit=1000, page_token=token))
        for c in r["option_contracts"]:
            listed[c["symbol"]] = c
        token = r.get("next_page_token")
        if not token:
            break
    chain = options().get_option_chain(OptionChainRequest(
        underlying_symbol=stock, feed=OptionsFeed.INDICATIVE, type=kind,
        expiration_date_gte=lo, expiration_date_lte=hi))
    out = []
    for symbol, snap in chain.items():
        c, q = listed.get(symbol), snap.get("latestQuote") or {}
        if not c:
            continue
        out.append({"symbol": symbol, "strike": float(c["strike_price"]),
                    "expiry": date.fromisoformat(c["expiration_date"]),
                    "delta": (snap.get("greeks") or {}).get("delta"),
                    "iv": snap.get("impliedVolatility"),
                    "bid": float(q.get("bp") or 0), "ask": float(q.get("ap") or 0),
                    "open_interest": int(c.get("open_interest") or 0), "penny": bool(c.get("ppind"))})
    return out


@retried
def option_quote(symbol):
    """Bid and ask of one option, for buying it back."""
    q = options().get_option_latest_quote(OptionLatestQuoteRequest(
        symbol_or_symbols=symbol, feed=OptionsFeed.INDICATIVE))[symbol]
    return {"bid": float(q.get("bp") or 0), "ask": float(q.get("ap") or 0)}


# --- orders --------------------------------------------------------------------------------------

def _limit(symbol, qty, side, intent, price):
    return trading().submit_order(LimitOrderRequest(
        symbol=symbol, qty=qty, side=side, type=OrderType.LIMIT, time_in_force=TimeInForce.DAY,
        limit_price=price, position_intent=intent))


def sell_to_open(option, qty, price):
    return _limit(option, qty, OrderSide.SELL, PositionIntent.SELL_TO_OPEN, price)


def buy_to_close(option, qty, price):
    return _limit(option, qty, OrderSide.BUY, PositionIntent.BUY_TO_CLOSE, price)


def wait_order(order_id, seconds=60):
    """Poll an order until it fills, ends, or the time runs out; the order as it then is."""
    end = time.time() + seconds
    while True:
        o = trading().get_order_by_id(order_id)
        if o["status"] in ("filled", "canceled", "expired", "rejected") or time.time() >= end:
            return o
        time.sleep(2)


def wait_filled(order_id, seconds=60):
    """True if the order fills within the time."""
    return wait_order(order_id, seconds)["status"] == "filled"


def replace_price(order_id, price):
    """Ask a new price on an open order (Alpaca replaces it with a new order, which it returns)."""
    return trading().replace_order_by_id(order_id, ReplaceOrderRequest(limit_price=price))


def buy_shares(stock, qty):
    """A market buy of shares - only used to practise the call side (buy_shares.py)."""
    return trading().submit_order(MarketOrderRequest(
        symbol=stock, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))

