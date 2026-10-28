"""Filters for the screen. A filter is one file here with one function:

    def apply(symbols, market, settings):     # -> the symbols it keeps
        ...

`market` answers prices, closes and market caps (market.py); `settings` is the filter's own table
in wheel.toml, [filters.<file name>]. An optional describe(settings) gives the line the run prints."""
import importlib


def load(name):
    return importlib.import_module(f"filters.{name}")


def describe(name, settings):
    f = load(name)
    if hasattr(f, "describe"):
        return f.describe(settings)
    return (f.__doc__ or name).strip().splitlines()[0].rstrip(".")
