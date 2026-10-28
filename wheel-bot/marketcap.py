"""What the market_cap filter sees for a few stocks: the SEC's share count, Alpaca's price, and the
two multiplied - or why a stock has no market cap here.

  uv run marketcap.py WMT AAPL TM"""
import os
import sys
import tomllib
from datetime import date
from pathlib import Path

import broker
import sec


def line(symbol, counts, prices, us_only=True):
    """One stock as a line of text: its market cap, or why it has none. Pure, tested."""
    found = counts.get(symbol)
    if found is None:
        why = "no US share count at the SEC (a foreign company's ADR?)" if us_only else "no share count at the SEC"
        return f"{symbol:<6} {why}"
    if symbol not in prices:
        return f"{symbol:<6} no price from Alpaca"
    cap = found["shares"] * prices[symbol]
    size = f"${cap / 1e12:.2f} trillion" if cap >= 1e12 else f"${cap / 1e9:,.0f} billion"
    return (f"{symbol:<6} {found['shares']:>15,.0f} shares ({found['source']}, {found['as_of']})"
            f" x ${prices[symbol]:,.2f} = {size}")


def main(argv=None):
    symbols = [s.upper() for s in (argv or sys.argv[1:])]
    settings = tomllib.loads((Path(__file__).parent / "wheel.toml").read_text())["filters"]["market_cap"]
    agent = os.environ.get("SEC_USER_AGENT") or settings.get("sec_user_agent")
    try:
        counts = sec.share_counts(agent, date.today(), settings.get("us_only", True))
    except RuntimeError as e:
        print(f"No share counts: {e}")
        return
    print(f"SEC share counts kept: {len(counts):,} tickers ({'US companies only' if settings.get('us_only', True) else 'all'})")
    prices = broker.prices([s for s in symbols if s in counts])
    for s in symbols:
        print(line(s, counts, prices, settings.get("us_only", True)))


if __name__ == "__main__":
    main()
