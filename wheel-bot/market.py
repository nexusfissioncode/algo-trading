"""What filters may ask about stocks. Each answer is fetched once per run and shared, so two
filters that both need closing prices cost one download."""
import os
from datetime import date

import broker
import sec


class Market:
    def __init__(self, settings, today=None, source=broker):
        self.settings, self.today, self.source = settings, today or date.today(), source
        self.names = {}       # symbol -> company name, filled by the screen
        self.notes = {}       # symbol -> {"RSI": 25.2, ...}, printed beside each pick
        self._prices, self._closes, self._shares = {}, {}, None

    def prices(self, symbols):
        missing = [s for s in symbols if s not in self._prices]
        if missing:
            self._prices.update(self.source.prices(missing))
        return {s: self._prices[s] for s in symbols if s in self._prices}

    def closes(self, symbols, days):
        missing = [s for s in symbols if len(self._closes.get(s, [])) < days]
        if missing:
            self._closes.update(self.source.closes(missing, days))
        return {s: self._closes.get(s, []) for s in symbols}

    def market_caps(self, symbols, us_only=True):
        """Shares (from the SEC) times the last price. Stocks the SEC has no count for are left out."""
        if self._shares is None:
            agent = os.environ.get("SEC_USER_AGENT") or \
                self.settings["filters"]["market_cap"].get("sec_user_agent")
            self._shares = sec.share_counts(agent, self.today, us_only)
        known = [s for s in symbols if s in self._shares]
        price = self.prices(known)
        return {s: self._shares[s]["shares"] * price[s] for s in known if s in price}

    def note(self, symbol, label, value):
        self.notes.setdefault(symbol, {})[label] = value
