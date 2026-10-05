"""The desk's logic, with the agents and the broker faked: no network, no Claude, no orders."""
import asyncio
import json

import pytest

import agent
import analyst
import desk
import guard
import market
import risk
import trader

BUY = {"symbol": "BTC/USD", "side": "buy", "conviction": "medium", "price": 64000.0, "rsi_14h": 41.0,
       "case": "Pulled back to the middle of the range on quiet news.", "risks": "A break of the day's low."}


def test_rsi_rises_with_gains_and_is_100_without_losses():
    assert market.rsi_of(list(range(1, 30))) == 100.0
    mixed = [10, 11, 10.5, 11.5, 11, 12, 11.4, 12.4, 12, 13, 12.6, 13.4, 13, 14, 13.5, 14.5]
    assert 50 < market.rsi_of(mixed) < 100


def test_summarize_reads_a_day_of_hourly_closes():
    closes = [100.0] * 80 + [100 + i for i in range(25)]
    s = market.summarize("BTC/USD", closes)
    assert s["price"] == 124 and s["high_24h"] == 124 and s["low_24h"] == 100
    assert s["change_24h_pct"] == 24.0


def test_guard_refuses_each_rule_in_words():
    assert guard.check("BTC/USD", "buy", 500, False, 0) == []
    assert "never double up" in guard.check("BTC/USD", "buy", 500, True, 0)[0]
    assert "over the limit" in guard.check("BTC/USD", "buy", 5000, False, 0)[0]
    assert "not on the list" in guard.check("DOGE/USD", "buy", 10, False, 0)[0]
    assert "no more buys" in guard.check("BTC/USD", "buy", 10, False, -250)[0]
    assert guard.check("BTC/USD", "sell", 0, True, -500) == [], "selling is always allowed"


def test_guard_place_never_reaches_the_broker_when_a_rule_is_broken(monkeypatch):
    monkeypatch.setattr(market, "account", lambda s: {"holding": {"qty": "0.01", "value": 640}, "open_orders": 0, "today_pnl": 0})
    monkeypatch.setattr(market, "trading", lambda: pytest.fail("the broker was called"))
    out = guard.place("BTC/USD", "buy", 500)
    assert out["placed"] is False and "never double up" in out["refused_because"][0]


def test_the_hook_lets_the_signed_order_through_and_nothing_else():
    signed = {"symbol": "BTC/USD", "side": "buy", "dollars": 500.0}
    hook = trader.lock_to(signed)
    allow = asyncio.run(hook({"tool_input": {"symbol": "BTC/USD", "side": "buy", "dollars": 500}}, "t1", None))
    assert allow == {}
    deny = asyncio.run(hook({"tool_input": {"symbol": "BTC/USD", "side": "buy", "dollars": 5000}}, "t2", None))
    out = deny["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "dollars 5000, signed 500.0" in out["permissionDecisionReason"]
    assert trader.differs(signed, {"symbol": "ETH/USD", "side": "buy", "dollars": 500}) == ["symbol 'ETH/USD', signed 'BTC/USD'"]


def test_signed_order_is_decided_in_code_and_capped_by_the_rules():
    assert desk.signed_order(BUY, {"decision": "veto", "dollars": 500}) is None
    assert desk.signed_order({**BUY, "side": "none"}, {"decision": "approve", "dollars": 500}) is None
    assert desk.signed_order(BUY, {"decision": "approve", "dollars": 0}) is None
    assert desk.signed_order(BUY, {"decision": "resize", "dollars": 250}) == {"symbol": "BTC/USD", "side": "buy", "dollars": 250.0}
    big = desk.signed_order(BUY, {"decision": "approve", "dollars": 99999})
    assert big["dollars"] == guard.RULES["max_dollars_per_order"]


def fake_desk(monkeypatch, tmp_path, verdict):
    calls = []

    async def fake_analyst(symbol):
        return {**BUY, "symbol": symbol}

    async def fake_risk(ticket):
        calls.append(("risk", ticket))
        return verdict

    async def fake_trader(order):
        calls.append(("trader", order))
        return {"placed": True, "broker_said": "accepted"}

    monkeypatch.setattr(desk, "analyst", fake_analyst)
    monkeypatch.setattr(desk, "risk", fake_risk)
    monkeypatch.setattr(desk, "trader", fake_trader)
    monkeypatch.setattr(desk, "LOG", tmp_path / "desk-log.jsonl")
    return calls


def test_a_veto_ends_the_run_and_the_trader_is_never_called(monkeypatch, tmp_path, capsys):
    calls = fake_desk(monkeypatch, tmp_path, {"decision": "veto", "dollars": 0, "checks": [], "reason": "already holding BTC/USD"})
    entry = asyncio.run(desk.one("BTC/USD"))
    assert [c[0] for c in calls] == ["risk"]
    assert entry["outcome"] == "vetoed"
    assert entry["verdict"]["reason"] == "already holding BTC/USD", "the reason is kept in the log"
    out = capsys.readouterr().out
    assert "VETO BTC/USD - the trader is never called" in out
    assert "TICKET BTC/USD  analyst -> risk" in out and "VERDICT BTC/USD  risk -> desk" in out
    assert json.loads((tmp_path / "desk-log.jsonl").read_text())["outcome"].startswith("vetoed")


def test_an_approval_hands_the_trader_exactly_the_signed_order(monkeypatch, tmp_path):
    calls = fake_desk(monkeypatch, tmp_path, {"decision": "approve", "dollars": 500, "checks": [], "reason": "fits"})
    entry = asyncio.run(desk.one("BTC/USD"))
    assert calls[1] == ("trader", {"symbol": "BTC/USD", "side": "buy", "dollars": 500.0})
    assert entry["outcome"] == "placed"


def test_each_agent_has_only_its_own_tools():
    assert [t.name for t in analyst.TOOLS] == ["snapshot", "news"]
    assert [t.name for t in risk.TOOLS] == ["account"]
    assert [t.name for t in trader.TOOLS] == ["place_order"]
    assert risk.VERDICT["properties"]["dollars"]["maximum"] == guard.RULES["max_dollars_per_order"]
    assert set(analyst.TICKET["required"]) == set(analyst.TICKET["properties"])


def test_a_run_goes_over_every_coin_on_the_list(monkeypatch, tmp_path):
    calls = fake_desk(monkeypatch, tmp_path, {"decision": "veto", "dollars": 0, "checks": [], "reason": "no"})
    entries = asyncio.run(desk.run(["BTC/USD", "ETH/USD"]))
    assert [e["symbol"] for e in entries] == ["BTC/USD", "ETH/USD"]
    assert [c[1]["symbol"] for c in calls] == ["BTC/USD", "ETH/USD"]
    assert len((tmp_path / "desk-log.jsonl").read_text().splitlines()) == 2


def test_an_agent_gets_only_its_tools_and_the_hook_watches_only_those():
    opts = agent.options_for("trader", instructions="i", answer=trader.REPORT, tools=trader.TOOLS,
                             before_tool=trader.lock_to({"symbol": "BTC/USD", "side": "buy", "dollars": 1}))
    assert opts.tools == [] and opts.permission_mode == "dontAsk" and opts.setting_sources == []
    assert opts.allowed_tools == ["mcp__trader__place_order"]
    matcher = opts.hooks["PreToolUse"][0].matcher
    assert matcher == "mcp__trader__place_order", "a hook on every tool also refuses the step that returns the answer"
    assert agent.options_for("analyst", instructions="i", answer={}, tools=analyst.TOOLS).hooks is None
