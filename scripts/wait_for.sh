#!/usr/bin/env bash
set -euo pipefail

URL="${1:-}"
TIMEOUT="${2:-120}"
if [[ -z "$URL" ]]; then
  echo "Usage: $0 <url> [timeout_seconds]" >&2
  exit 1
fi

echo "Waiting for $URL (timeout ${TIMEOUT}s)..."
end=$((SECONDS + TIMEOUT))
until curl -fsS "$URL" >/dev/null 2>&1; do
  if (( SECONDS >= end )); then
    echo "Timeout waiting for $URL" >&2
    exit 1
  fi
  sleep 2
done
echo "OK: $URL"

