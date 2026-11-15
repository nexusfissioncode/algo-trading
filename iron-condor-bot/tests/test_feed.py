"""The replay's stock bars come from the bot's own free feed, unless that feed has a hole in the day."""
from datetime import datetime

from alpaca.data.enums import DataFeed


def bars_by_feed(monkeypatch, counts):
    import broker
    asked = []

    class Stocks:
        def get_stock_bars(self, req):
            asked.append(req.feed)
            return {"SPY": [{"t": i, "c": 1.0} for i in range(counts[req.feed])]}
    monkeypatch.setattr(broker, "stocks", lambda: Stocks())
    return broker, asked


START = datetime(2025, 3, 10, 9, 30)


def test_a_normal_day_stays_on_the_bots_own_feed(monkeypatch):
    broker, asked = bars_by_feed(monkeypatch, {DataFeed.IEX: 204, DataFeed.SIP: 481})
    assert len(broker.stock_minutes("SPY", START, START)) == 204      # a half day is a normal day
    assert asked == [DataFeed.IEX]


def test_a_day_with_a_hole_in_the_free_feed_is_not_lost(monkeypatch, capsys):
    broker, asked = bars_by_feed(monkeypatch, {DataFeed.IEX: 0, DataFeed.SIP: 481})
    assert len(broker.stock_minutes("SPY", START, START)) == 481
    assert asked == [DataFeed.IEX, DataFeed.SIP]
    assert "2025-03-10  0 IEX bars" in capsys.readouterr().out
