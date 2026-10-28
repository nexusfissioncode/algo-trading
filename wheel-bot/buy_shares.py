"""Buy shares at the market, to practise the call side without waiting for an assignment.

  uv run buy_shares.py BAC 100

An assignment would leave the same thing in the account: a hundred shares per contract, at the
put's strike. Here they come at the market price instead. Paper account only."""
import sys

import broker


def main(argv=None):
    stock, qty = (argv or sys.argv[1:])[:2]
    order = broker.buy_shares(stock.upper(), int(qty))
    print(f"buy {qty} {stock.upper()} at the market -> order {order['status']}")
    if broker.wait_filled(order["id"], 30):
        print("filled - the next run of wheel.py sees the shares")
    else:
        print("not filled yet (is the market open?)")


if __name__ == "__main__":
    main()
