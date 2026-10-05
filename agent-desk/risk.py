"""The risk manager: reads the analyst's ticket and the account, and says yes, smaller, or no.
It sees the ticket, not the analyst's whole conversation - and it cannot trade either."""
import asyncio
import json
import sys

import market
from agent import STRONG, as_tool, run_agent
from guard import RULES

INSTRUCTIONS = f"""You are the risk manager on a small crypto trading desk. You get the analyst's
ticket. Check the account, then decide: "approve", "resize" or "veto". You never place orders.
Your rules:
- Size by conviction: low 250 dollars, medium 500, high {RULES['max_dollars_per_order']}.
  Never more than {RULES['max_dollars_per_order']} dollars, and never more than a tenth of the cash.
- Never double up: if the account already holds the coin or has an open order for it, veto.
- If today's loss is {RULES['max_loss_per_day']} dollars or more, veto.
- A ticket with side "none" is a veto with nothing to check.
- Weigh the analyst's case against its risks and the numbers on the ticket: if the case does not
  hold up, resize down or veto, and say why.
Put each rule you checked in "checks", in a few words each."""

VERDICT = {
    "type": "object",
    "properties": {
        "decision": {"enum": ["approve", "resize", "veto"]},
        "dollars": {"type": "number", "minimum": 0, "maximum": RULES["max_dollars_per_order"]},
        "checks": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["decision", "dollars", "checks", "reason"],
    "additionalProperties": False,
}

TOOLS = [as_tool("account", "Cash, equity, today's profit or loss, and the position and open orders"
                 " in a coin.", {"symbol": str}, market.account)]


async def risk(ticket):
    return await run_agent("risk", task="The analyst's ticket:\n" + json.dumps(ticket, indent=2),
                           instructions=INSTRUCTIONS, answer=VERDICT, tools=TOOLS, model=STRONG)


if __name__ == "__main__":
    ticket = json.load(open(sys.argv[1]))
    print(json.dumps(asyncio.run(risk(ticket)), indent=2, ensure_ascii=False))
