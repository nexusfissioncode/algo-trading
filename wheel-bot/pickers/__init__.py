"""Pickers decide which stocks may get a new put. A picker is one file here with one function:

    def pick(market, settings, say):     # -> a list of symbols
        ...

`settings` is the whole of wheel.toml; `say` prints a line of the run. Name the file in
wheel.toml (picker = "...") or on the command line (--picker ...)."""
import importlib


def load(name):
    return importlib.import_module(f"pickers.{name}")
