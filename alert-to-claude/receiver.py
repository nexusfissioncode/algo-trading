#!/usr/bin/env python3
"""A TradingView alert wakes Claude.

Listens on http://localhost:8765/alert. Each alert is checked for the secret, then handed to
Claude Code in headless mode (claude -p), which reads the account through the Alpaca MCP server,
follows rules.md, and places the order or says why it skipped. Paper account only.

Standard library only: nothing to pip install.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765
SECRET = os.environ.get("ALERT_SECRET", "")
HERE = os.path.dirname(os.path.abspath(__file__))
ALERTS = queue.Queue()   # one at a time, in the order they arrived

# The lock: the only tools Claude may use. Nothing else - no shell, no files, no web.
TOOLS = [
    "mcp__alpaca__get_account_info",
    "mcp__alpaca__get_all_positions",
    "mcp__alpaca__get_orders",
    "mcp__alpaca__get_crypto_latest_quote",
    "mcp__alpaca__get_crypto_latest_trade",
    "mcp__alpaca__get_crypto_snapshot",
    "mcp__alpaca__place_crypto_order",
    "mcp__alpaca__close_position",
]


def say(line=""):
    print(line, flush=True)


def hidden(key):
    k = key.lower()
    return k == "id" or k.endswith("_id") or "account" in k or "number" in k


# the fields worth a glance, by the names people use for them
READABLE = {"symbol": "symbol", "side": "side", "qty": "qty", "notional": "notional", "type": "type",
            "status": "status", "p": "price", "ap": "ask", "bp": "bid", "filled_avg_price": "filled at",
            "cash": "cash", "buying_power": "buying power", "market_value": "value"}


def facts(value, out):
    """The few readable facts in a tool's answer: prices, sizes, statuses - never ids."""
    if isinstance(value, dict):
        for k, v in value.items():
            if hidden(k):
                continue
            if isinstance(v, (dict, list)):
                if isinstance(v, list) and not v:
                    out.append(f"{k}=none")
                facts(v, out)
            elif k in READABLE and v not in (None, ""):
                out.append(f"{READABLE[k]}={v}")
    elif isinstance(value, list):
        for v in value[:2]:
            facts(v, out)
    return out


def short(text, width=78):
    """One line of a tool's answer."""
    try:
        data = json.loads(text)
        data = data.get("data", data) if isinstance(data, dict) else data
        line = " ".join(facts(data, [])) or "ok"
    except ValueError:
        line = " | ".join(l.strip() for l in str(text).splitlines()
                          if l.strip() and not hidden(l.split(":")[0].strip().replace(" ", "_")))
    return line if len(line) <= width else line[: width - 3] + "..."


def ask_claude(alert):
    """Run Claude once, headless, and print each step it takes as it takes it."""
    prompt = "A TradingView alert just arrived:\n" + json.dumps(alert) + "\nFollow your rules."
    with open(os.path.join(HERE, "rules.md")) as f:
        rules = f.read()
    cmd = ["claude", "-p", prompt,
           "--mcp-config", os.path.join(HERE, ".mcp.json"), "--strict-mcp-config",
           "--tools", "",
           "--allowedTools", ",".join(TOOLS),
           "--permission-mode", "dontAsk",      # anything not on the list is refused, never asked
           "--append-system-prompt", rules,
           "--output-format", "stream-json", "--verbose"]
    decision = "no answer from Claude"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=HERE) as p:
        for raw in p.stdout:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            for part in (msg.get("message") or {}).get("content") or []:
                if part.get("type") == "tool_use":
                    name = part["name"].replace("mcp__alpaca__", "")
                    args = ", ".join(f"{k}={v}" for k, v in (part.get("input") or {}).items())
                    say(f"  claude -> {name}({args})")
                elif part.get("type") == "tool_result":
                    body = part.get("content")
                    if isinstance(body, list):
                        body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                    say(f"  alpaca <- {short(body)}")
            if msg.get("type") == "result":
                answer = msg.get("result") or ""
                lines = [l for l in answer.splitlines() if l.startswith("DECISION:")]
                decision = lines[-1] if lines else "no DECISION line - Claude said: " + answer[:200]
    say("  " + decision)
    with open(os.path.join(HERE, "decisions.log"), "a") as log:
        log.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "alert": alert, "decision": decision}) + "\n")


def worker():
    while True:
        alert = ALERTS.get()
        say()
        say(f"alert received: {alert.get('action')} {alert.get('ticker')} at {alert.get('price')}")
        ask_claude(alert)


class Alerts(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            alert = json.loads(body)
        except ValueError:
            alert = {}
        if not SECRET or alert.pop("secret", None) != SECRET:
            self.send_response(401)
            self.end_headers()
            say("rejected: wrong secret - Claude was not woken")
            return
        self.send_response(200)          # answer TradingView at once; it waits only a few seconds
        self.send_header("Content-Length", "3")
        self.end_headers()
        self.wfile.write(b"ok\n")
        ALERTS.put(alert)                # Claude works on it in the background

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not SECRET:
        sys.exit("set ALERT_SECRET first, so only your alerts are accepted")
    threading.Thread(target=worker, daemon=True).start()
    say(f"listening on http://localhost:{PORT}/alert")
    HTTPServer(("127.0.0.1", PORT), Alerts).serve_forever()
