#!/usr/bin/env bash
set -euo pipefail

API_HOST=${API_HOST:-localhost}
API_PORT=${API_PORT:-8000}
BASE_URL=${BASE_URL:-http://$API_HOST:$API_PORT}

DIR=$(cd "$(dirname "$0")" && pwd)
"$DIR/wait_for.sh" "$BASE_URL/health" 120

echo "Health:" && (command -v jq >/dev/null 2>&1 && curl -s "$BASE_URL/health" | jq . || curl -s "$BASE_URL/health")

echo "Scoring payments..."
curl -s -X POST "$BASE_URL/score" -H 'Content-Type: application/json' \
  -d '{"source":"payments","payload":{"amount":129.5,"currency":"USD","user_id":"u1","device_id":"d1","merchant_name":"ACME","country":"US"}}' | tee /tmp/score_payments.json

echo "Scoring sms..."
curl -s -X POST "$BASE_URL/score" -H 'Content-Type: application/json' \
  -d '{"source":"sms","payload":{"message_text":"Your OTP is 123456","user_id":"u2"}}' | tee /tmp/score_sms.json

echo "Scoring email..."
curl -s -X POST "$BASE_URL/score" -H 'Content-Type: application/json' \
  -d '{"source":"email","payload":{"subject":"Welcome","body":"Hello","sender_domain":"news.com","user_id":"u3"}}' | tee /tmp/score_email.json

for f in /tmp/score_payments.json /tmp/score_sms.json /tmp/score_email.json; do
  python - <<PY || { echo "Smoke check failed: $f missing expected keys" >&2; exit 1; }
import json,sys
data=json.load(open('$f'))
assert 'score' in data and 'is_alert' in data and 'reasons' in data
PY
done

echo "Prometheus metrics head:"
curl -s "$BASE_URL/metrics" | head -n 20

echo "SMOKE OK"
