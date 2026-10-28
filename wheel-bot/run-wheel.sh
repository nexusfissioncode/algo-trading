#!/bin/bash
# What cron runs once a day. Cron starts with almost nothing set - no keys, and a short PATH -
# so this script sets both, then runs the wheel once and adds what it printed to runs.log.
#
# keys.env sits next to this script, readable only by you (chmod 600), and is never committed:
#   ALPACA_API_KEY=...
#   ALPACA_SECRET_KEY=...
#   SEC_USER_AGENT="Your Name your-email@example.com"
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f keys.env ]; then
  echo "no keys.env next to run-wheel.sh - see the comment at the top" >&2
  exit 1
fi
set -a; source ./keys.env; set +a
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
{ echo "=== $(date)"; uv run wheel.py --trade; } >> runs.log 2>&1
