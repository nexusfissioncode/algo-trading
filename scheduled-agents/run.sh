#!/bin/bash
# Runs one skill with nobody at the keyboard:  ./run.sh morning-brief
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
# Claude finds MCP tools through a built-in search tool; with built-in tools off it must load them all
export ENABLE_TOOL_SEARCH=false

if [ -f .env ]; then                # on the laptop: the keys from a file only you can read
  set -a; source ./.env; set +a
else                                # on the server: fetched from Secret Manager at every run
  for NAME in ALPACA_API_KEY ALPACA_SECRET_KEY CLAUDE_CODE_OAUTH_TOKEN; do
    export "$NAME=$(gcloud secrets versions access latest --secret "$NAME")"
  done
fi

SKILL="$1"
OUT="reports/$(date +%F)-$SKILL.md"
LOG=/dev/null
if [ "$SKILL" = trade-journal ]; then LOG=journal.md; fi
READ_ONLY="mcp__guard__rsi,mcp__alpaca__get_account_info,mcp__alpaca__get_all_positions,mcp__alpaca__get_orders,mcp__alpaca__get_crypto_snapshot,mcp__alpaca__get_crypto_bars,mcp__alpaca__get_news"
trap 'echo "$(date "+%F %H:%M") $SKILL failed" | tee -a runs.log' ERR
mkdir -p reports
touch journal.md

tail -n 40 journal.md | claude -p "/$SKILL today is $(date "+%A %-d %B")" \
  --strict-mcp-config --mcp-config .mcp.json \
  --tools "" --allowedTools "$READ_ONLY" \
  --permission-mode dontAsk | tee "$OUT" | tee -a "$LOG"

echo "$(date "+%F %H:%M") $SKILL saved $OUT" | tee -a runs.log
