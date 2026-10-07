"""The numbers a strategy can ask for, on 1-hour or 1-day bars. Plain Python on Alpaca's prices.
With a snapshot file, every agent reads the same numbers from it - the same minute for every run.

  uv run python indicators.py BTC/USD --needs price,rsi14,sma50
  uv run python indicators.py BTC/USD ETH/USD --save snapshot.json      (freeze every number)"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

NAMES = "price, change24h, high24h, low24h, rsiN, smaN, emaN (N a number of bars, like rsi14 or sma50)"
TIMEFRAMES = ("1h", "1d")


def sma(closes, n):
    """The average of the last n closes."""
    return sum(closes[-n:]) / n


def ema(closes, n):
    """An average that weighs recent closes more: each new close moves it 2/(n+1) of the way."""
    k, value = 2 / (n + 1), sum(closes[:n]) / n
    for c in closes[n:]:
        value += k * (c - value)
    return value


def rsi(closes, n=14):
    """Wilder's RSI: average gain against average loss, on a scale of 0 to 100."""
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(c, 0) for c in changes[:n]) / n
    loss = sum(max(-c, 0) for c in changes[:n]) / n
    for c in changes[n:]:
        gain = (gain * (n - 1) + max(c, 0)) / n
        loss = (loss * (n - 1) + max(-c, 0)) / n
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def value(name, closes, per_day):
    """One named number from a list of closes (oldest first). Raises on a name it does not know."""
    day = closes[-(per_day + 1):]
    if name == "price":
        return closes[-1]
    if name == "change24h":
        return (day[-1] / day[0] - 1) * 100
    if name == "high24h":
        return max(day)
    if name == "low24h":
        return min(day)
    m = re.fullmatch(r"(rsi|sma|ema)(\d+)", name)
    if not m:
        raise ValueError(f"unknown number {name!r}: use {NAMES}")
    kind, n = m.group(1), int(m.group(2))
    if len(closes) < n + 1:
        raise ValueError(f"{name} needs {n + 1} bars, only {len(closes)} available")
    return {"rsi": rsi, "sma": sma, "ema": ema}[kind](closes, n)


def compute(closes, needs, per_day):
    return {name: round(value(name, closes, per_day), 2) for name in needs}


def closes(symbol, timeframe="1h", bars=220):
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    unit = TimeFrame.Hour if timeframe == "1h" else TimeFrame.Day
    start = datetime.now(timezone.utc) - (timedelta(hours=bars) if timeframe == "1h" else timedelta(days=bars))
    data = CryptoHistoricalDataClient().get_crypto_bars(
        CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=unit, start=start))
    return [b.close for b in data.data[symbol]]


def numbers(symbol, needs, timeframe="1h"):
    """What the agents call: from the snapshot when there is one, else live."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe is 1h or 1d, not {timeframe!r}")
    snap = os.environ.get("DESK_SNAPSHOT")
    if snap:
        frozen = json.load(open(snap))[symbol][timeframe]
        missing = [n for n in needs if n not in frozen]
        if missing:
            raise ValueError(f"the snapshot has no {', '.join(missing)}")
        return {"symbol": symbol, "timeframe": timeframe, "at": json.load(open(snap))["at"],
                **{n: frozen[n] for n in needs}}
    per_day = 24 if timeframe == "1h" else 1
    return {"symbol": symbol, "timeframe": timeframe, **compute(closes(symbol, timeframe), needs, per_day)}


FROZEN = ["price", "change24h", "high24h", "low24h", "rsi14", "sma20", "sma50", "ema20"]

if __name__ == "__main__":
    args = sys.argv[1:]
    symbols = [a for a in args if "/" in a]
    if "--save" in args:
        out = args[args.index("--save") + 1]
        snap = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        for s in symbols:
            snap[s] = {tf: compute(closes(s, tf), FROZEN, 24 if tf == "1h" else 1) for tf in TIMEFRAMES}
        json.dump(snap, open(out, "w"), indent=2)
        print(f"froze {len(FROZEN)} numbers for {', '.join(symbols)} at {snap['at']} into {out}")
    else:
        needs = args[args.index("--needs") + 1].split(",") if "--needs" in args else ["price", "rsi14"]
        tf = args[args.index("--timeframe") + 1] if "--timeframe" in args else "1h"
        for s in symbols:
            print(json.dumps(numbers(s, needs, tf)))
