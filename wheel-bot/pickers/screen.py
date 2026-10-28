"""Every US stock with options on Alpaca, through the filters named in [screen], in order."""
import filters


def pick(market, settings, say):
    universe = market.source.stocks_with_options()
    market.names.update({a["symbol"]: a["name"] for a in universe})
    symbols = sorted(a["symbol"] for a in universe)
    say(f"  start           {len(symbols):>5,}   stocks with options on Alpaca")
    for name in settings["screen"]["filters"]:
        own = settings.get("filters", {}).get(name, {})
        symbols = filters.load(name).apply(symbols, market, own)
        say(f"  {name:<15} {len(symbols):>5,}   {filters.describe(name, own)}")
        if not symbols:
            break
    return symbols
