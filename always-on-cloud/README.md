# always-on-cloud

The alert bot on a free Google Cloud e2-micro, always on: systemd, Caddy, keys in Secret Manager.

Paper trading only; code to learn from, not financial advice. Every command, in order:

```text
FREE TIER: https://cloud.google.com/free/docs/free-cloud-features#compute

GCLOUD (on your laptop): https://cloud.google.com/sdk/docs/install
gcloud init
PROJECT=$(gcloud config get project); echo $PROJECT

THE MACHINE
gcloud services enable compute.googleapis.com secretmanager.googleapis.com billingbudgets.googleapis.com
BILLING=$(gcloud billing projects describe $PROJECT --format "value(billingAccountName.basename())")
gcloud billing budgets create --billing-account $BILLING --display-name alert-bot --budget-amount 1USD --filter-projects projects/$PROJECT --threshold-rule percent=0.5 --threshold-rule percent=1.0
gcloud compute addresses create alert-bot-ip --region us-west1
gcloud compute addresses describe alert-bot-ip --region us-west1 --format "value(address)"
gcloud compute instances create alert-bot --zone us-west1-b --machine-type e2-micro --image-family debian-12 --image-project debian-cloud --boot-disk-size 30GB --boot-disk-type pd-standard --address alert-bot-ip --tags alert-bot --scopes cloud-platform
gcloud compute firewall-rules create alert-bot-https --allow tcp:80,tcp:443 --target-tags alert-bot

INSIDE THE MACHINE
gcloud compute ssh trader@alert-bot --zone us-west1-b
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
sudo apt-get update -qq && sudo apt-get install -y -qq caddy python3 curl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://claude.ai/install.sh | bash
export PATH=$HOME/.local/bin:$PATH
exit

THE SECRETS (from environment variables on your laptop)
claude setup-token
read -s CLAUDE_CODE_OAUTH_TOKEN
export CLAUDE_CODE_OAUTH_TOKEN
printf %s "$ALPACA_API_KEY" | gcloud secrets create alpaca-api-key --data-file=-
printf %s "$ALPACA_SECRET_KEY" | gcloud secrets create alpaca-secret-key --data-file=-
printf %s "$CLAUDE_CODE_OAUTH_TOKEN" | gcloud secrets create claude-token --data-file=-
export ALERT_SECRET=pick-a-long-secret
printf %s "$ALERT_SECRET" | gcloud secrets create alert-secret --data-file=-
SA=$(gcloud compute instances describe alert-bot --zone us-west1-b --format "value(serviceAccounts[0].email)")
gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA --role roles/secretmanager.secretAccessor --condition None --format none

THE BOT (receiver.py, rules.md, .mcp.json from alert-to-claude, plus:)

start.sh
#!/bin/sh
s() { gcloud secrets versions access latest --secret "$1"; }
export ALERT_SECRET="$(s alert-secret)"
export ALPACA_API_KEY="$(s alpaca-api-key)"
export ALPACA_SECRET_KEY="$(s alpaca-secret-key)"
export CLAUDE_CODE_OAUTH_TOKEN="$(s claude-token)"
exec python3 receiver.py

alert-bot.service
[Unit]
Description=TradingView alert to Claude to Alpaca
After=network-online.target
[Service]
User=trader
WorkingDirectory=/home/trader/alert-bot
Environment=PATH=/home/trader/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/bin/sh start.sh
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target

Caddyfile
HOST {
	reverse_proxy localhost:8765
}

gcloud compute ssh trader@alert-bot --zone us-west1-b --command "mkdir -p alert-bot"
gcloud compute scp receiver.py rules.md .mcp.json start.sh alert-bot.service Caddyfile trader@alert-bot:alert-bot/ --zone us-west1-b
gcloud compute ssh trader@alert-bot --zone us-west1-b
sudo cp alert-bot/alert-bot.service /etc/systemd/system/ && sudo systemctl enable --now alert-bot
systemctl is-active alert-bot

HTTPS
sed "s/HOST/YOUR.IP.ADDRESS.sslip.io/" alert-bot/Caddyfile | sudo tee /etc/caddy/Caddyfile
sudo systemctl reload caddy && exit
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://YOUR.IP.ADDRESS.sslip.io/alert -d "{}"

TRADINGVIEW
Alert, Notifications, Webhook URL:
https://YOUR.IP.ADDRESS.sslip.io/alert
Message:
{"secret":"pick-a-long-secret","ticker":"{{ticker}}","action":"buy","price":{{close}}}
(strategy alerts: "action":"{{strategy.order.action}}")

PROOF AND LOGS
gcloud compute ssh trader@alert-bot --zone us-west1-b --command "sudo reboot"
journalctl -u alert-bot -f -o cat
tail -n 1 alert-bot/decisions.log

TURNING IT OFF
gcloud compute instances stop alert-bot --zone us-west1-b
gcloud projects delete $PROJECT
```
