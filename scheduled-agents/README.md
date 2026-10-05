# scheduled-agents

Every command from the video, as in its description.

```text
Every command from the video, in order. Paper trading only; education, not financial advice.

EARLIER IN THE SERIES
Claude and Alpaca, by chat: https://youtu.be/EYmt8iX31ao
An alert wakes Claude: https://youtu.be/SED4Wyf82l0
Always on, for free: https://youtu.be/K26jC0z6n2w
Your rules, in code (the guard): https://youtu.be/b_npdVpQN9k

SETUP
Claude Code: https://code.claude.com/docs/en/setup  uv: https://docs.astral.sh/uv/
claude mcp add alpaca --scope project -e 'ALPACA_API_KEY=${ALPACA_API_KEY}' -e 'ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}' -e ALPACA_PAPER_TRADE=true -- uvx alpaca-mcp-server
claude mcp add guard --scope project -e 'ALPACA_API_KEY=${ALPACA_API_KEY}' -e 'ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}' -- uv run server.py
claude setup-token   (a sign-in token for runs with no browser; keep it secret)

.claude/skills/morning-brief/SKILL.md
---
name: morning-brief
description: A short morning brief on the paper account and the two coins it may trade. Use when asked for the morning brief.
---
Read only. Never place, change or cancel an order. 1. The account: equity, cash, change since yesterday's close. 2. Open positions and orders. 3. BTC/USD and ETH/USD: last price, 24-hour change, the 14-hour RSI from the guard's rsi tool. 4. The three headlines that matter most. 5. If last night's journal is in your input, one line on it. At most twelve short lines; end with one line starting "Watch:".

.claude/skills/trade-journal/SKILL.md: the same shape - today's orders, open positions and their profit or loss, the day's change, one line comparing with earlier entries in your input, one lesson. Start with "## " and the date.

THE KEYS IN A FILE (laptop)
touch .env; chmod 600 .env
then one line each: ALPACA_API_KEY=..., ALPACA_SECRET_KEY=..., CLAUDE_CODE_OAUTH_TOKEN=...

run.sh (the parts that matter)
set -euo pipefail   # a failed run is logged as failed
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
export ENABLE_TOOL_SEARCH=false   # with built-in tools off, MCP tools load only with this
if [ -f .env ]; then set -a; source ./.env; set +a
else for NAME in ALPACA_API_KEY ALPACA_SECRET_KEY CLAUDE_CODE_OAUTH_TOKEN; do
  export "$NAME=$(gcloud secrets versions access latest --secret "$NAME")"; done; fi
READ_ONLY="mcp__guard__rsi,mcp__alpaca__get_account_info,mcp__alpaca__get_all_positions,mcp__alpaca__get_orders,mcp__alpaca__get_crypto_snapshot,mcp__alpaca__get_crypto_bars,mcp__alpaca__get_news"
tail -n 40 journal.md | claude -p "/$SKILL today is $(date "+%A %-d %B")" --strict-mcp-config --mcp-config .mcp.json --tools "" --allowedTools "$READ_ONLY" --permission-mode dontAsk | tee "$OUT"
echo "$(date "+%F %H:%M") $SKILL saved $OUT" | tee -a runs.log

THE SERVER (from the laptop)
PROJECT=$(gcloud config get project)
gcloud services enable compute.googleapis.com secretmanager.googleapis.com billingbudgets.googleapis.com
gcloud billing budgets create --billing-account $BILLING --display-name desk --budget-amount 1USD --filter-projects projects/$PROJECT --threshold-rule percent=0.5
gcloud compute instances create desk --zone us-west1-a --machine-type e2-micro --image-family debian-12 --image-project debian-cloud --boot-disk-size 30GB --boot-disk-type pd-standard --scopes cloud-platform
gcloud compute ssh trader@desk --zone us-west1-a
  (swap file, then) curl -LsSf https://astral.sh/uv/install.sh | sh
  curl -fsSL https://claude.ai/install.sh | bash
printf %s "$ALPACA_API_KEY" | gcloud secrets create ALPACA_API_KEY --data-file=-   (and the other two)
gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA --role roles/secretmanager.secretAccessor --condition None
gcloud compute scp --recurse .claude .mcp.json CLAUDE.md rules.json server.py run.sh schedule.cron trader@desk:desk/ --zone us-west1-a

schedule.cron
30 6 * * *   /home/trader/desk/run.sh morning-brief
0 17 * * *   /home/trader/desk/run.sh trade-journal

ON THE SERVER
sudo timedatectl set-timezone America/Los_Angeles
crontab schedule.cron; crontab -l
tail -F runs.log

TURNING IT OFF
crontab -r   (on the server), then: gcloud projects delete $PROJECT
```
