"""A strategy is a file in plain English. This loads one, and keeps the rule that a strategy may
only trade after it has been read back without open questions (readback.py)."""
import hashlib
import json
import re
from pathlib import Path

SECTIONS = ["Coins", "Entry (buy)", "Size", "Exit (sell the whole position)"]


def load(path):
    """The file's text, its name, its coins and its sections."""
    text = Path(path).read_text()
    name = re.search(r"^# Strategy: (.+)$", text, re.M)
    sections = dict(re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S))
    coins = re.findall(r"[A-Z]{2,5}/USD", sections.get("Coins", ""))
    return {"path": str(path), "name": name.group(1).strip() if name else Path(path).stem, "text": text,
            "coins": coins, "sections": {k.strip(): v.strip() for k, v in sections.items()},
            "missing": [s for s in SECTIONS if s not in sections]}


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def readback_file(path):
    return Path(path).with_suffix(".readback.json")


def cleared(strat):
    """Why this strategy may not trade yet, or None. Its read-back must be current and clean."""
    rb = readback_file(strat["path"])
    if not rb.exists():
        return "it has not been read back yet: run readback.py on it first"
    saved = json.loads(rb.read_text())
    if saved["fingerprint"] != fingerprint(strat["text"]):
        return "the file has changed since it was read back: run readback.py again"
    if saved["questions"]:
        return f"its read-back left {len(saved['questions'])} open question(s): fix the file and read it back"
    return None
