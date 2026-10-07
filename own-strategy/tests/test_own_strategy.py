"""Bring your own strategy, with the agents and the broker faked: no network, no Claude, no orders."""
import asyncio
import json
import shutil
from pathlib import Path

import pytest

import desk
import guard
import indicators
import readback
import strategy
import trader

HERE = Path(__file__).parent.parent


def test_moving_averages_and_rsi():
    closes = [float(x) for x in range(1, 61)]
    assert indicators.sma(closes, 10) == 55.5
    assert indicators.ema(closes, 10) == pytest.approx(55.5, abs=0.01), "a steady climb: ema sits on the sma"
    assert indicators.rsi(closes, 14) == 100.0
    assert 0 < indicators.rsi([10, 9, 10, 8, 9, 7, 8, 6, 7, 5, 6, 4, 5, 3, 4, 2, 3], 14) < 50


def test_named_numbers_and_unknown_names():
    closes = [100.0] * 30 + [100 + i for i in range(25)]
    got = indicators.compute(closes, ["price", "change24h", "high24h", "low24h", "sma5"], per_day=24)
    assert got == {"price": 124, "change24h": 24.0, "high24h": 124, "low24h": 100, "sma5": 122.0}
    with pytest.raises(ValueError, match="unknown number 'momentum'"):
        indicators.value("momentum", closes, 24)
    with pytest.raises(ValueError, match="needs 201 bars"):
        indicators.value("sma200", closes, 24)


def test_a_snapshot_freezes_the_numbers(tmp_path, monkeypatch):
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps({"at": "2026-10-07 01:00 UTC", "BTC/USD": {"1h": {"price": 1.0, "rsi14": 37.0}, "1d": {}}}))
    monkeypatch.setenv("DESK_SNAPSHOT", str(snap))
    monkeypatch.setattr(indicators, "closes", lambda *a: pytest.fail("went live with a snapshot set"))
    assert indicators.numbers("BTC/USD", ["rsi14"]) == {"symbol": "BTC/USD", "timeframe": "1h",
                                                        "at": "2026-10-07 01:00 UTC", "rsi14": 37.0}
    with pytest.raises(ValueError, match="no sma50"):
        indicators.numbers("BTC/USD", ["sma50"])


def test_the_example_strategies_have_every_section():
    for name in ["template", "rsi-dip", "trend"]:
        s = strategy.load(HERE / "strategies" / f"{name}.md")
        assert s["missing"] == [], name
        assert s["coins"] == ["BTC/USD", "ETH/USD"], name
    assert strategy.load(HERE / "strategies" / "rsi-dip.md")["name"] == "RSI dip buy"
    vague = strategy.load(HERE / "strategies" / "vague.md")
    assert vague["coins"] == ["BTC/USD"]
    for name in ["rsi-dip", "trend"]:
        assert "not advice" in (HERE / "strategies" / f"{name}.md").read_text(), "examples are marked placeholders"


def test_code_adds_its_own_questions():
    s = strategy.load(HERE / "strategies" / "vague.md")
    s["missing"] = ["Do nothing when"]
    qs = readback.code_questions(s, {"needs": ["rsi14", "momentum", "avg_entry"]})
    assert "the file has no 'Do nothing when' section" in qs
    assert "'momentum' is not a number the desk can measure" in qs
    assert not any("rsi14" in q or "avg_entry" in q for q in qs)


def test_the_desk_trades_only_a_strategy_read_back_clean(tmp_path):
    path = tmp_path / "mine.md"
    shutil.copy(HERE / "strategies" / "trend.md", path)
    s = strategy.load(path)
    assert "not been read back" in strategy.cleared(s)
    rb = strategy.readback_file(path)
    rb.write_text(json.dumps({"fingerprint": strategy.fingerprint(s["text"]), "questions": ["what is a lot?"]}))
    assert "1 open question" in strategy.cleared(s)
    rb.write_text(json.dumps({"fingerprint": strategy.fingerprint(s["text"]), "questions": []}))
    assert strategy.cleared(s) is None
    path.write_text(s["text"] + "\nOne more rule.\n")
    assert "changed since it was read back" in strategy.cleared(strategy.load(path))
    with pytest.raises(SystemExit, match="will not trade"):
        asyncio.run(desk.run(strategy.load(path)))


def test_signed_orders_buy_sell_and_veto():
    buy = {"symbol": "BTC/USD", "side": "buy", "dollars": 250}
    assert desk.signed_order(buy, {"decision": "approve", "dollars": 250}) == {"symbol": "BTC/USD", "side": "buy", "dollars": 250.0}
    assert desk.signed_order(buy, {"decision": "approve", "dollars": 900})["dollars"] == 250.0, "never above the strategy's size"
    assert desk.signed_order(buy, {"decision": "veto", "dollars": 0}) is None
    sell = {"symbol": "ETH/USD", "side": "sell", "dollars": 0}
    assert desk.signed_order(sell, {"decision": "approve", "dollars": 0}) == {"symbol": "ETH/USD", "side": "sell", "dollars": 0}
    assert desk.signed_order({**buy, "side": "none"}, {"decision": "approve", "dollars": 250}) is None


def test_the_hook_matches_a_sell_by_side_and_symbol():
    signed = {"symbol": "ETH/USD", "side": "sell", "dollars": 0}
    assert trader.differs(signed, {"symbol": "ETH/USD", "side": "sell", "dollars": 0}) == []
    assert trader.differs(signed, {"symbol": "ETH/USD", "side": "buy", "dollars": 0}) == ["side 'buy', signed 'sell'"]


def test_the_guard_will_not_sell_what_is_not_held():
    assert guard.check("BTC/USD", "sell", 0, False, 0) == ["no BTC/USD position to sell"]
    assert guard.check("BTC/USD", "sell", 0, True, -500) == []


def test_a_run_follows_the_strategy_through_every_seat(monkeypatch, tmp_path):
    path = tmp_path / "trend.md"
    shutil.copy(HERE / "strategies" / "trend.md", path)
    s = strategy.load(path)
    strategy.readback_file(path).write_text(json.dumps({"fingerprint": strategy.fingerprint(s["text"]), "questions": []}))
    seen = []

    async def fake_analyst(symbol, strat):
        seen.append(("analyst", strat["name"]))
        side = "sell" if symbol == "ETH/USD" else "buy"
        return {"symbol": symbol, "side": side, "rule": "exit 1" if side == "sell" else "entry 1",
                "evidence": "price above sma50", "dollars": 250 if side == "buy" else 0}

    async def fake_risk(ticket, strat):
        seen.append(("risk", strat["name"]))
        return {"decision": "approve", "dollars": ticket["dollars"], "checks": [], "reason": "rule holds"}

    async def fake_trader(order):
        seen.append(("trader", order["side"]))
        return {"placed": True, "broker_said": "ok"}

    monkeypatch.setattr(desk, "analyst", fake_analyst)
    monkeypatch.setattr(desk, "risk", fake_risk)
    monkeypatch.setattr(desk, "trader", fake_trader)
    monkeypatch.setattr(desk, "LOG", tmp_path / "log.jsonl")
    entries = asyncio.run(desk.run(strategy.load(path)))
    assert [e["outcome"] for e in entries] == ["bought", "sold"]
    assert ("analyst", "Trend follow") in seen and ("risk", "Trend follow") in seen
    assert [x for x in seen if x[0] == "trader"] == [("trader", "buy"), ("trader", "sell")]
    assert all(json.loads(l)["strategy"] == "Trend follow" for l in (tmp_path / "log.jsonl").read_text().splitlines())
