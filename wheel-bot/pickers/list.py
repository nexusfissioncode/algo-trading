"""Your own stocks, exactly as written in wheel.toml under [list]."""


def pick(market, settings, say):
    symbols = [s.upper() for s in settings["list"]["symbols"]]
    say(f"  your list       {len(symbols):>5}   {', '.join(symbols)}")
    return symbols
