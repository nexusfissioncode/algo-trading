"""The trader: places the order risk signed - that order and no other.
Three locks: it is the only agent with an order tool; the tool is the guard (your rules in code);
and a hook checks every call against the signed order before it runs."""
import asyncio
import json
import sys

import guard
from agent import FAST, as_tool, run_agent

INSTRUCTIONS = """You are the trader on a small crypto trading desk. You are handed an order that
risk has signed - a buy for some dollars, or a sell of the whole position. Place it with
place_order, exactly as signed, once. Then report what the broker
said. If the order is refused, do not try again or change it - report the refusal."""

REPORT = {
    "type": "object",
    "properties": {
        "placed": {"type": "boolean"},
        "broker_said": {"type": "string"},
    },
    "required": ["placed", "broker_said"],
    "additionalProperties": False,
}

TOOLS = [as_tool("place_order", "Buy a coin for a number of dollars, or sell (side sell) the whole"
                 " position, in the paper account, if the rules allow it.", {"symbol": str, "side": str, "dollars": float},
                 guard.place)]


def differs(signed, call):
    """How a tool call differs from the signed order, in words. Empty means it is the same order."""
    out = []
    for key in ("symbol", "side"):
        if call.get(key) != signed[key]:
            out.append(f"{key} {call.get(key)!r}, signed {signed[key]!r}")
    if signed["side"] == "buy" and abs(float(call.get("dollars", 0)) - float(signed["dollars"])) > 0.005:
        out.append(f"dollars {call.get('dollars')}, signed {signed['dollars']}")
    return out


def lock_to(signed):
    """A hook: the SDK runs it before every tool call, and it can say no."""
    async def before_tool(data, tool_use_id, context):
        wrong = differs(signed, data["tool_input"])
        if not wrong:
            return {}
        why = "; ".join(wrong)
        print(f"  hook     REFUSED {data['tool_input']}: {why}", file=sys.stderr, flush=True)
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "not the order risk signed: " + why}}
    return before_tool


async def trader(signed, asked=None):
    """Place the signed order. `asked`: what the trader is told, if someone says something else."""
    order = asked or signed
    if order["side"] == "sell":
        task = f"Place this order: sell the whole {order['symbol']} position (side sell, dollars 0)."
    else:
        task = f"Place this order: buy {order['dollars']} dollars of {order['symbol']}."
    return await run_agent("trader", task=task, instructions=INSTRUCTIONS, answer=REPORT,
                           tools=TOOLS, model=FAST, before_tool=lock_to(signed))


if __name__ == "__main__":
    # python trader.py BTC/USD 500            place a signed order of 500 dollars
    # python trader.py BTC/USD 500 --ask 5000 risk signed 500, but the trader is told 5000
    symbol, dollars = sys.argv[1], float(sys.argv[2])
    signed = {"symbol": symbol, "side": "buy", "dollars": dollars}
    asked = None
    if "--ask" in sys.argv:
        asked = {**signed, "dollars": float(sys.argv[sys.argv.index("--ask") + 1])}
    print(json.dumps(asyncio.run(trader(signed, asked)), indent=2))
