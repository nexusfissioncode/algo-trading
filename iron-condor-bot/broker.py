"""Everything that talks to Alpaca, in one place. Paper account only.

Keys come from the environment: ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys).
Answers are plain dicts (raw_data), so a new field on Alpaca's side never breaks a run."""
import functools
import os
import time
from datetime import datetime, timezone

from alpaca.data.enums import DataFeed, OptionsFeed
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import (OptionBarsRequest, OptionChainRequest, OptionLatestQuoteRequest,
                                 StockBarsRequest, StockLatestTradeRequest)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, OrderType, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest, ReplaceOrderRequest
from requests.exceptions import ConnectionError, Timeout


def retried(fn):
    """Try a read again after a dropped connection: a bot that watches all day should not stop for
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


def kind(symbol):
    """'C' or 'P', read off an option symbol such as SPY261026P00755000."""
    return symbol[-9]


def strike(symbol):
    return int(symbol[-8:]) / 1000


# --- the account ---------------------------------------------------------------------------------

@retried
def positions():
    return trading().get_all_positions()


@retried
def clock():
    return trading().get_clock()


# --- prices --------------------------------------------------------------------------------------

@retried
def price(stock):
    """The last trade (the free IEX feed)."""
    return float(stocks().get_stock_latest_trade(StockLatestTradeRequest(
        symbol_or_symbols=stock, feed=DataFeed.IEX))[stock]["p"])


@retried
def chain(stock, expiry, low, high):
    """Every call and put of one expiry with strikes between low and high, with bid and ask
    (the free indicative feed)."""
    snaps = options().get_option_chain(OptionChainRequest(
        underlying_symbol=stock, feed=OptionsFeed.INDICATIVE, expiration_date=expiry,
        strike_price_gte=low, strike_price_lte=high))
    out = []
    for symbol, snap in snaps.items():
        q = snap.get("latestQuote") or {}
        out.append({"symbol": symbol, "strike": strike(symbol), "type": kind(symbol),
                    "bid": float(q.get("bp") or 0), "ask": float(q.get("ap") or 0)})
    return out


@retried
def quotes(symbols):
    got = options().get_option_latest_quote(OptionLatestQuoteRequest(
        symbol_or_symbols=list(symbols), feed=OptionsFeed.INDICATIVE))
    return {s: {"bid": float(q.get("bp") or 0), "ask": float(q.get("ap") or 0)} for s, q in got.items()}


@retried
def stock_minutes(stock, start, end):
    """One-minute bars, for replaying a past day: [{t, c}], oldest first."""
    bars = stocks().get_stock_bars(StockBarsRequest(
        symbol_or_symbols=stock, timeframe=TimeFrame.Minute, start=start, end=end, feed=DataFeed.IEX))
    return [{"t": b["t"], "c": b["c"]} for b in bars.get(stock, [])]


@retried
def option_minutes(symbols, start, end):
    """One-minute bars of options (expired ones too): {symbol: [{t, c}]}."""
    out = {}
    symbols = list(symbols)
    for i in range(0, len(symbols), 100):
        bars = options().get_option_bars(OptionBarsRequest(
            symbol_or_symbols=symbols[i:i + 100], timeframe=TimeFrame.Minute, start=start, end=end))
        for s, rows in bars.items():
            out[s] = [{"t": b["t"], "c": b["c"]} for b in rows]
    return out


# --- orders --------------------------------------------------------------------------------------

LEGS_OPEN = {"short_put": (OrderSide.SELL, PositionIntent.SELL_TO_OPEN),
             "long_put": (OrderSide.BUY, PositionIntent.BUY_TO_OPEN),
             "short_call": (OrderSide.SELL, PositionIntent.SELL_TO_OPEN),
             "long_call": (OrderSide.BUY, PositionIntent.BUY_TO_OPEN)}
LEGS_CLOSE = {"short_put": (OrderSide.BUY, PositionIntent.BUY_TO_CLOSE),
              "long_put": (OrderSide.SELL, PositionIntent.SELL_TO_CLOSE),
              "short_call": (OrderSide.BUY, PositionIntent.BUY_TO_CLOSE),
              "long_call": (OrderSide.SELL, PositionIntent.SELL_TO_CLOSE)}


def _mleg(condor, qty, net, sides):
    """One order for all four legs. Alpaca writes a net credit as a negative price, a net debit
    as a positive one."""
    legs = [OptionLegRequest(symbol=leg["symbol"], ratio_qty=1, side=sides[name][0], position_intent=sides[name][1])
            for name, leg in condor["legs"].items()]
    return trading().submit_order(LimitOrderRequest(
        qty=qty, order_class=OrderClass.MLEG, type=OrderType.LIMIT, time_in_force=TimeInForce.DAY,
        limit_price=round(net, 2), legs=legs))


def open_condor(condor, qty, credit):
    return _mleg(condor, qty, -credit, LEGS_OPEN)


def close_condor(condor, qty, cost):
    return _mleg(condor, qty, cost, LEGS_CLOSE)


def wait_order(order_id, seconds=60):
    """Poll an order until it fills, ends, or the time runs out; the order as it then is."""
    end = time.time() + seconds
    while True:
        o = trading().get_order_by_id(order_id)
        if o["status"] in ("filled", "canceled", "expired", "rejected") or time.time() >= end:
            return o
        time.sleep(1)


def replace_price(order_id, price):
    """Ask a new price on an open buy-back (Alpaca replaces it with a new order, which it returns)."""
    return trading().replace_order_by_id(order_id, ReplaceOrderRequest(limit_price=round(price, 2)))


def replace_credit(order_id, credit):
    return trading().replace_order_by_id(order_id, ReplaceOrderRequest(limit_price=round(-credit, 2)))


def cancel(order_id):
    try:
        trading().cancel_order_by_id(order_id)
    except Exception:          # already filled or gone: nothing to cancel
        pass


def now_utc():
    return datetime.now(timezone.utc)
