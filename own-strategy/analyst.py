"""The analyst: follows YOUR strategy file. It measures what the file asks for, checks each rule,
and writes one ticket that names the rule it followed. It can look; it cannot trade."""
import asyncio
import json
import sys

import indicators
import market
import strategy
from agent import FAST, as_tool, run_agent

BRIEF = """You are the analyst on a small crypto desk. You follow the strategy below exactly - it
is the only strategy there is. For the coin you are given: measure the numbers the strategy needs
with the indicators tool, check the position, then check the rules in order:
- holding the coin: if an exit rule is met, side "sell", else side "none"
- not holding: if a do-nothing rule is met, side "none"; else if an entry rule is met, side "buy"
In "rule" name the rule you followed, like "entry 1" or "exit 2", or "none fits".
In "evidence" give the numbers that decided it, like "rsi14(1h) 37.2 < 40". Never use a number you
did not measure. "dollars" is the strategy's size for a buy, else 0.

THE STRATEGY:
"""

TICKET = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "side": {"enum": ["buy", "sell", "none"]},
        "rule": {"type": "string"},
        "evidence": {"type": "string"},
        "dollars": {"type": "number", "minimum": 0},
    },
    "required": ["symbol", "side", "rule", "evidence", "dollars"],
    "additionalProperties": False,
}


def measure(symbol, needs, timeframe="1h"):
    return indicators.numbers(symbol, [n.strip() for n in needs.split(",") if n.strip()], timeframe)


def position(symbol):
    a = market.account(symbol)
    return {"symbol": symbol, "position": a["position"], "open_orders": a["open_orders"]}


TOOLS = [
    as_tool("indicators", "Numbers for a coin: needs is a comma list like price,rsi14,sma50; "
            "timeframe is 1h or 1d.", {"symbol": str, "needs": str, "timeframe": str}, measure),
    as_tool("position", "Whether the account holds a coin, and its average entry price.",
            {"symbol": str}, position),
]


async def analyst(symbol, strat):
    return await run_agent("analyst", task=f"Write the ticket for {symbol}.",
                           instructions=BRIEF + strat["text"], answer=TICKET, tools=TOOLS, model=FAST)


if __name__ == "__main__":
    strat = strategy.load(sys.argv[1])
    ticket = asyncio.run(analyst(sys.argv[2] if len(sys.argv) > 2 else strat["coins"][0], strat))
    print(json.dumps(ticket, indent=2, ensure_ascii=False))
