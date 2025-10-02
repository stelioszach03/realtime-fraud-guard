#!/usr/bin/env bash
set -euo pipefail

attempts=0
max_attempts=3

fix_and_retry() {
  attempts=$((attempts+1))
  if (( attempts > max_attempts )); then
    echo "Max attempts reached. Aborting." >&2
    exit 1
  fi
  echo "Attempt $attempts/$max_attempts: applying common fixes and retrying..." >&2
  # Ensure PYTHONPATH in Dockerfile
  if ! grep -q 'PYTHONPATH=/app' Dockerfile; then
    echo "Adding PYTHONPATH to Dockerfile" >&2
    sed -i 's/^ENV PYTHONDONTWRITEBYTECODE/ENV PYTHONDONTWRITEBYTECODE=1 \\\n    PYTHONUNBUFFERED=1 \\\n    PIP_NO_CACHE_DIR=1 \\\n    PYTHONPATH=\/app/' Dockerfile || true
  fi
  docker compose build --no-cache --pull api || true
}

docker compose up -d --build

# Tail kafka readiness briefly
(docker compose logs -f kafka & sleep 10; pkill -P $$ -f 'docker compose logs -f kafka' || true) || true

# Run topics init if service missing (compat)
if ! docker compose ps topics >/dev/null 2>&1; then
  echo "Running topics bootstrap via script..."
  bash scripts/bootstrap_topics.sh || true
else
  docker compose run --rm topics || true
fi

# Run tests inside api container; capture on failure
if ! docker compose exec -T api pytest -q; then
  ts=$(date +%s)
  mkdir -p artifacts
  docker compose exec -T api pytest -q || true | tee "artifacts/pytest-$ts.log" || true
  fix_and_retry
  docker compose up -d --build
  docker compose exec -T api pytest -q || true
fi

bash scripts/smoke.sh || {
  fix_and_retry
  docker compose up -d --build
  bash scripts/smoke.sh || exit 1
}

echo "URLs:"
echo "REST:       http://localhost:8000"
echo "Prometheus: http://localhost:9090"
echo "Grafana:    http://localhost:3000"
echo "gRPC:       localhost:50051"

