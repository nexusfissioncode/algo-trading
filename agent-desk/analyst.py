"""The analyst: reads the market and the news, and writes up one idea as a ticket.
It can look - it has no tool that touches the account or places an order."""
import asyncio
import json
import sys

import market
from agent import FAST, as_tool, run_agent

INSTRUCTIONS = """You are the analyst on a small crypto desk that takes small swing positions.
Look at the price, the RSI and the latest news for the coin you are given; write ONE ticket.
Propose "buy" unless there is a clear red flag: RSI above 90, or news of a crash, a hack or
a ban - then side is "none". The more stretched the market, the lower the conviction.
Conviction is low, medium or high. In "case", say why buying makes sense, in two sentences
a person can check against the numbers. In "risks", say what could go wrong, as plainly.
You do not decide the size and you cannot trade: risk and the trader do that after you."""

TICKET = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "side": {"enum": ["buy", "none"]},
        "conviction": {"enum": ["low", "medium", "high"]},
        "price": {"type": "number"},
        "rsi_14h": {"type": "number"},
        "case": {"type": "string"},
        "risks": {"type": "string"},
    },
    "required": ["symbol", "side", "conviction", "price", "rsi_14h", "case", "risks"],
    "additionalProperties": False,
}

TOOLS = [
    as_tool("snapshot", "Price, 24 hour change, high, low and 14 hour RSI of a coin, like BTC/USD.",
            {"symbol": str}, market.snapshot),
    as_tool("news", "The latest headlines that mention a coin, like BTC/USD.",
            {"symbol": str}, market.news),
]


async def analyst(symbol):
    return await run_agent("analyst", task=f"Write the ticket for {symbol}.",
                           instructions=INSTRUCTIONS, answer=TICKET, tools=TOOLS, model=FAST)


if __name__ == "__main__":
    ticket = asyncio.run(analyst(sys.argv[1] if len(sys.argv) > 1 else "BTC/USD"))
    print(json.dumps(ticket, indent=2, ensure_ascii=False))
