"""The desk, now with your strategy: plain Python that hands the ticket from seat to seat.
It refuses a strategy that has not been read back, and a veto ends the run.

  uv run python desk.py --strategy strategies/rsi-dip.md
  uv run python desk.py --strategy strategies/trend.md --snapshot snapshot.json"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import strategy
from analyst import analyst
from guard import RULES
from risk import risk
from trader import trader

LOG = Path(__file__).parent / "desk-log.jsonl"


def handoff(label, payload):
    print(f"\n{label}\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n", flush=True)


def signed_order(ticket, verdict):
    """The order risk signed, or None. Checked in code, whatever the agents wrote."""
    if verdict["decision"] != "approve" or ticket["side"] not in ("buy", "sell"):
        return None
    if ticket["side"] == "sell":
        return {"symbol": ticket["symbol"], "side": "sell", "dollars": 0}
    dollars = min(float(verdict["dollars"]), float(ticket["dollars"]), RULES["max_dollars_per_order"])
    return {"symbol": ticket["symbol"], "side": "buy", "dollars": dollars} if dollars > 0 else None


async def one(symbol, strat):
    print(f"\ndesk: {symbol} with '{strat['name']}', {datetime.now(timezone.utc):%H:%M} UTC", flush=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbol": symbol,
             "strategy": strat["name"]}
    entry["ticket"] = ticket = await analyst(symbol, strat)
    handoff(f"TICKET {symbol}  analyst -> risk  ({ticket['rule']})", ticket)
    if ticket["side"] == "none":
        entry["outcome"] = "nothing to do"
    else:
        entry["verdict"] = verdict = await risk(ticket, strat)
        handoff(f"VERDICT {symbol}  risk -> desk", verdict)
        order = signed_order(ticket, verdict)
        if not order:
            entry["outcome"] = "vetoed"
            print(f"VETO {symbol} - the trader is never called.", flush=True)
        else:
            handoff(f"SIGNED ORDER {symbol}  desk -> trader", order)
            entry["report"] = report = await trader(order)
            handoff(f"REPORT {symbol}  trader -> desk", report)
            entry["outcome"] = ("bought" if order["side"] == "buy" else "sold") if report["placed"] else "refused"
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"desk: {symbol} {entry['outcome']} - logged to {LOG.name}", flush=True)
    return entry


async def run(strat, symbols=None):
    why = strategy.cleared(strat)
    if why:
        raise SystemExit(f"desk: will not trade '{strat['name']}' - {why}")
    return [await one(s, strat) for s in (symbols or strat["coins"])]


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


if __name__ == "__main__":
    if arg("--snapshot"):
        os.environ["DESK_SNAPSHOT"] = arg("--snapshot")
    coins = [a for a in sys.argv[1:] if "/" in a and not a.endswith(".md") and not a.endswith(".json")]
    asyncio.run(run(strategy.load(arg("--strategy")), coins or None))
