#!/bin/sh
# Start the receiver with its secrets fetched from Google Secret Manager.
# They live in this process's memory only: never in a file on the server, never in the code.
# The VM may read them because its service account was given the Secret Accessor role.
s() { gcloud secrets versions access latest --secret "$1"; }
export ALERT_SECRET="$(s alert-secret)"
export ALPACA_API_KEY="$(s alpaca-api-key)"
export ALPACA_SECRET_KEY="$(s alpaca-secret-key)"
export CLAUDE_CODE_OAUTH_TOKEN="$(s claude-token)"
exec python3 receiver.py
