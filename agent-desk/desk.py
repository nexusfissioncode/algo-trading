"""The desk: plain Python, not another AI. It hands the ticket from seat to seat, and it is the
code - not a model - that decides a veto ends the run."""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from analyst import analyst
from guard import RULES
from risk import risk
from trader import trader

LOG = Path(__file__).parent / "desk-log.jsonl"


def handoff(label, payload):
    print(f"\n{label}\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n", flush=True)


def signed_order(ticket, verdict):
    """The order risk signed, or None. Checked in code, whatever the agents wrote."""
    if ticket["side"] != "buy" or verdict["decision"] == "veto":
        return None
    dollars = min(float(verdict["dollars"]), RULES["max_dollars_per_order"])
    return {"symbol": ticket["symbol"], "side": "buy", "dollars": dollars} if dollars > 0 else None


async def one(symbol):
    print(f"\ndesk: {symbol}, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", flush=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbol": symbol}

    entry["ticket"] = ticket = await analyst(symbol)
    handoff(f"TICKET {symbol}  analyst -> risk", ticket)
    if ticket["side"] != "buy":
        entry["outcome"] = "no idea today"
    else:
        entry["verdict"] = verdict = await risk(ticket)
        handoff(f"VERDICT {symbol}  risk -> desk", verdict)
        order = signed_order(ticket, verdict)
        if not order:
            entry["outcome"] = "vetoed"
            print(f"VETO {symbol} - the trader is never called.", flush=True)
        else:
            handoff(f"SIGNED ORDER {symbol}  desk -> trader", order)
            entry["report"] = report = await trader(order)
            handoff(f"REPORT {symbol}  trader -> desk", report)
            entry["outcome"] = "placed" if report["placed"] else "refused"

    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"desk: {symbol} {entry['outcome']} - logged to {LOG.name}", flush=True)
    return entry


async def run(symbols):
    """One pass of the desk over every coin it is allowed to trade."""
    return [await one(s) for s in symbols]


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1:] or RULES["symbols"]))
