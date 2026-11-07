"""When to get out. Pure: the condor, today's quotes, the price and the clock in; a decision out.

Four rules, checked in order; the first that fires wins:
  take_profit  buying it back costs (1 - take_profit) of the credit or less: that share is kept
  stop         buying it back costs `stop` times the credit or more
  touch        the price has reached a short strike
  close_by     it is that time or later: close whatever happens

Alpaca's broker holds no stop for an options order (they are market or limit), so these rules
live here, in the program, and the program has to be running to use them."""
from datetime import time

RULES = ("take_profit", "stop", "touch", "close_by")


def hhmm(text):
    h, m = text.split(":")
    return time(int(h), int(m))


def cost_to_close(condor, quotes):
    """What buying the condor back costs per share at the mids: the shorts back, the wings sold.
    None when a leg has no quote."""
    q = {name: quotes.get(leg["symbol"]) for name, leg in condor["legs"].items()}
    if any(v is None or v["ask"] <= 0 for v in q.values()):
        return None
    m = {name: (v["bid"] + v["ask"]) / 2 for name, v in q.items()}
    return round(max(0.0, m["short_put"] + m["short_call"] - m["long_put"] - m["long_call"]), 2)


def targets(condor, rules):
    """The buy-back prices that fire the two money rules."""
    credit = condor["credit"]
    return {"take_profit": round(credit * (1 - rules["take_profit"]), 2),
            "stop": round(credit * rules["stop"], 2)}


def check(condor, cost, price, now, rules):
    """The first rule that fires, as (rule, why), or None to hold. `now` is New York time."""
    keep, stop = targets(condor, rules).values()
    sp, sc = condor["legs"]["short_put"]["strike"], condor["legs"]["short_call"]["strike"]
    if cost is not None and cost <= keep:
        return "take_profit", f"buy back for {cost:.2f}, at or under {keep:.2f}"
    if cost is not None and cost >= stop:
        return "stop", f"buy back for {cost:.2f}, at or over {stop:.2f}"
    if rules.get("touch") and (price <= sp or price >= sc):
        return "touch", f"{price:.2f} reached the short strike {sp if price <= sp else sc:g}"
    if now.time() >= hhmm(rules["close_by"]):
        return "close_by", f"it is {now:%H:%M}, the closing time is {rules['close_by']}"
    return None


def pnl(condor, cost, contracts):
    """Dollars made (or lost, negative) if bought back at `cost` now."""
    return round((condor["credit"] - cost) * 100 * contracts, 2)
