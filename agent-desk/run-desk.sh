#!/bin/bash
# One pass of the desk with nobody at the keyboard:  ./run-desk.sh
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

if [ -f .env ]; then                # on the laptop: the keys from a file only you can read
  set -a; source ./.env; set +a
else                                # on the server: fetched from Secret Manager at every run
  for NAME in ALPACA_API_KEY ALPACA_SECRET_KEY CLAUDE_CODE_OAUTH_TOKEN; do
    export "$NAME=$(gcloud secrets versions access latest --secret "$NAME")"
  done
fi

trap 'echo "$(date "+%F %H:%M") desk failed" | tee -a runs.log' ERR
uv run -q python desk.py 2>&1 | tee -a desk-runs.txt | grep "logged to" | cut -c 7-110 \
  | sed "s/^/$(date "+%F %H:%M") /" | tee -a runs.log
