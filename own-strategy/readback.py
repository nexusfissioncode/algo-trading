"""Read it back: before a strategy may trade, an agent restates every rule as a condition a machine
can check, and lists anything it would have to guess. Any open question, and the desk refuses it.

  uv run python readback.py strategies/rsi-dip.md"""
import asyncio
import json
import re
import sys

import strategy
from agent import STRONG, run_agent

INSTRUCTIONS = """You read a trading strategy written in plain English, before anyone trades with it.
Restate every rule as a condition a machine can check, using only these numbers: price, change24h,
high24h, low24h, rsiN, smaN, emaN (N a number of bars), each on 1-hour or 1-day bars, plus the
position's avg_entry. Write the condition like: rsi14(1h) < 40.
The desk always works like this, so do not ask about it: each coin is run on its own; it holds at
most one position per coin and never buys more of a coin it holds; "do nothing" rules block buys
only, never exits; price is the latest close; change24h is a percent; it checks the rules each
time the desk runs.
If a rule has no number, no comparison or no timeframe - a word like strong, cheap, a lot,
sensible - do not guess: put a question in "questions" saying exactly what is missing.
In "needs" list only the bare names of numbers the rules use, like rsi14 or sma50.
Do not judge whether the strategy is good. Only whether it can be followed without guessing."""

READBACK = {
    "type": "object",
    "properties": {
        "rules": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "says": {"type": "string"}, "check": {"type": "string"}},
            "required": ["id", "says", "check"], "additionalProperties": False}},
        "needs": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rules", "needs", "questions"],
    "additionalProperties": False,
}

KNOWN = re.compile(r"(price|change24h|high24h|low24h|avg_entry|(rsi|sma|ema)\d+)$")


def code_questions(strat, answer):
    """What code can see for itself, whatever the agent said."""
    qs = [f"the file has no '{s}' section" for s in strat["missing"]]
    if "Coins" not in strat["missing"] and not strat["coins"]:
        qs.append("no coin is named like BTC/USD")
    names = [n.split("(")[0].strip() for n in answer["needs"]]
    qs += [f"'{n}' is not a number the desk can measure" for n in names if n and not KNOWN.match(n)]
    return qs


async def readback(path):
    strat = strategy.load(path)
    answer = await run_agent("readback", task="The strategy file:\n\n" + strat["text"],
                             instructions=INSTRUCTIONS, answer=READBACK, model=STRONG)
    answer["questions"] = code_questions(strat, answer) + answer["questions"]
    answer.update(strategy=strat["name"], fingerprint=strategy.fingerprint(strat["text"]))
    strategy.readback_file(path).write_text(json.dumps(answer, indent=2))
    return answer


def show(answer):
    print(f"\nREAD BACK  {answer['strategy']}")
    for r in answer["rules"]:
        print(f"  {r['id']:<10} {r['check']}")
    print(f"  numbers   {', '.join(answer['needs']) or '-'}")
    if answer["questions"]:
        print(f"\nQUESTIONS ({len(answer['questions'])})")
        for q in answer["questions"]:
            print(f"  ? {q}")
        print("\nREFUSED - fix the file, then read it back again.")
    else:
        print("\nACCEPTED - every rule can be checked without guessing.")


if __name__ == "__main__":
    result = asyncio.run(readback(sys.argv[1]))
    show(result)
    sys.exit(1 if result["questions"] else 0)
