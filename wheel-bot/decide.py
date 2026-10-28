"""The wheel's decisions. Pure: what the account holds goes in, what to do comes out.
No network here, so every branch is tested on made-up positions (tests/test_decide.py).

The bot keeps no state of its own. Each run reads the account and works out where each stock is
on the wheel: a short put open, shares held, a short call open, or nothing yet."""
import re
from dataclasses import dataclass, field
from datetime import date

OCC = re.compile(r"^([A-Z.]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def parse_option(symbol):
    """'BAC261127P00047000' -> ('BAC', date(2026, 11, 27), 'put', 47.0); a stock -> None."""
    m = OCC.match(symbol)
    if not m:
        return None
    root, yy, mm, dd, kind, strike = m.groups()
    return root, date(2000 + int(yy), int(mm), int(dd)), "put" if kind == "P" else "call", int(strike) / 1000


@dataclass
class Short:
    """An option the account has sold and not yet bought back."""
    symbol: str
    kind: str          # "put" or "call"
    strike: float
    expiry: date
    qty: int           # contracts, counted positive
    entry: float       # premium received, per share
    now: float         # what it would cost to buy back, per share


@dataclass
class Stock:
    """Everything the account holds in one stock."""
    shares: int = 0
    cost: float = 0.0  # average price paid per share
    shorts: list = field(default_factory=list)


@dataclass
class Action:
    symbol: str        # the stock
    do: str            # "sell put", "sell call", "buy back", "roll", "hold", "wait"
    why: str
    option: Short = None
    qty: int = 0
    cost: float = 0.0  # what the shares cost, for a call's strike


def holdings(positions):
    """Group Alpaca's positions by stock."""
    stocks = {}
    for p in positions:
        qty = int(float(p["qty"]))
        opt = parse_option(p["symbol"])
        if opt is None:
            s = stocks.setdefault(p["symbol"], Stock())
            s.shares, s.cost = qty, float(p["avg_entry_price"])
            continue
        root, expiry, kind, strike = opt
        s = stocks.setdefault(root, Stock())
        if qty < 0:
            s.shorts.append(Short(p["symbol"], kind, strike, expiry, -qty,
                                  float(p["avg_entry_price"]), float(p["current_price"] or 0)))
    return stocks


def order_stocks(open_orders):
    """The stocks that open orders touch (a multi-leg order names them in its legs)."""
    stocks = set()
    for o in open_orders:
        for symbol in [o.get("symbol")] + [leg["symbol"] for leg in o.get("legs") or []]:
            if symbol:
                opt = parse_option(symbol)
                stocks.add(opt[0] if opt else symbol)
    return stocks


def decide(positions, open_orders, settings, today):
    """One or more actions for every stock already in the wheel."""
    manage = settings["manage"]
    busy = order_stocks(open_orders)
    actions = []
    for symbol, s in sorted(holdings(positions).items()):
        if symbol in busy:
            actions.append(Action(symbol, "wait", "an order is still open - see what it does first"))
            continue
        for short in s.shorts:
            action = manage_short(symbol, short, manage, today)
            action.cost = s.cost
            actions.append(action)
        covered = sum(x.qty for x in s.shorts if x.kind == "call") * 100
        free = s.shares - covered
        if free >= 100:
            actions.append(Action(symbol, "sell call",
                                  f"holding {s.shares} shares at {s.cost:.2f} - "
                                  f"{free // 100} contract(s) not yet covered", qty=free // 100, cost=s.cost))
        elif 0 < s.shares < 100 and not s.shorts:
            actions.append(Action(symbol, "hold", f"{s.shares} shares - a call needs 100"))
    # a stock with an order still open but nothing held yet (a put sent, not yet filled)
    for symbol in sorted(busy - set(holdings(positions))):
        actions.append(Action(symbol, "wait", "an order is still open - see what it does first"))
    return actions


def manage_short(symbol, short, manage, today):
    """Take profit, roll, or let it run."""
    days = (short.expiry - today).days
    made = (short.entry - short.now) / short.entry if short.entry else 0
    name = f"{short.kind} {short.strike:g}"
    if days <= 0:
        return Action(symbol, "hold", f"{name} expires today - Alpaca settles it after the close", short)
    if made >= manage["take_profit"]:
        return Action(symbol, "buy back", f"{name} has made {made:.0%} of its premium", short, short.qty)
    if days <= manage["roll_days"]:
        return Action(symbol, "roll", f"{name} has {days} days left", short, short.qty)
    return Action(symbol, "hold", f"{name}: {days} days left, {made:.0%} of the premium made", short)


def room_for_puts(positions, open_orders, settings):
    """How many new puts this run may sell, and which stocks may not get one."""
    in_wheel = set(holdings(positions)) | order_stocks(open_orders)
    put = settings["put"]
    return max(0, min(put["new_per_run"], put["max_stocks"] - len(in_wheel))), in_wheel
