"""The risk manager: holds the analyst to the strategy. It measures the numbers itself, checks
that the cited rule really holds, and applies the hard limits. It cannot trade."""
import asyncio
import json
import sys

import strategy
from agent import STRONG, as_tool, run_agent
from analyst import measure
from guard import RULES
import market

BRIEF = f"""You are the risk manager on a small crypto desk. The analyst's ticket must follow the
strategy below. Measure the numbers yourself with the indicators tool and check the account, then
decide "approve" or "veto". You never place orders.
- Veto a ticket that names no rule, or whose rule does not hold on the numbers you measured.
- Veto a buy if the account already holds the coin or has an open order for it.
- Veto a sell if the account does not hold the coin.
- A buy is at most the strategy's size, at most {RULES['max_dollars_per_order']} dollars, and at
  most a tenth of the cash.
- Veto a buy if today's loss is {RULES['max_loss_per_day']} dollars or more.
List what you checked in "checks", a few words each, with the numbers.

THE STRATEGY:
"""

VERDICT = {
    "type": "object",
    "properties": {
        "decision": {"enum": ["approve", "veto"]},
        "dollars": {"type": "number", "minimum": 0, "maximum": RULES["max_dollars_per_order"]},
        "checks": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["decision", "dollars", "checks", "reason"],
    "additionalProperties": False,
}

TOOLS = [
    as_tool("indicators", "Numbers for a coin: needs is a comma list like price,rsi14,sma50; "
            "timeframe is 1h or 1d.", {"symbol": str, "needs": str, "timeframe": str}, measure),
    as_tool("account", "Cash, today's profit or loss, the position in a coin and its open orders.",
            {"symbol": str}, market.account),
]


async def risk(ticket, strat):
    return await run_agent("risk", task="The analyst's ticket:\n" + json.dumps(ticket, indent=2),
                           instructions=BRIEF + strat["text"], answer=VERDICT, tools=TOOLS,
                           model=STRONG)


if __name__ == "__main__":
    strat = strategy.load(sys.argv[1])
    ticket = json.load(open(sys.argv[2]))
    print(json.dumps(asyncio.run(risk(ticket, strat)), indent=2, ensure_ascii=False))
