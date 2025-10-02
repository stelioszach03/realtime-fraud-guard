#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Kafka topics using kafka-topics CLI (idempotent)
# - payments: partitions=6, rf=1
# - sms:      partitions=3, rf=1
# - email:    partitions=3, rf=1
# - alerts:   partitions=3, rf=1

# Resolve broker(s) from environment
# Resolve brokers from env, otherwise pick sensible default based on context
RAW_BROKERS=${KAFKA_BROKER:-${KAFKA_BROKERS:-}}
if [[ -z "$RAW_BROKERS" ]]; then
  if command -v docker >/dev/null 2>&1 && docker network ls --format '{{.Name}}' | grep -q '^aegis-net$'; then
    RAW_BROKERS="kafka:9092"
  else
    RAW_BROKERS="localhost:9092"
  fi
fi
# Strip common schemes like PLAINTEXT://, SASL_PLAINTEXT://, SASL_SSL://, SSL://
BROKERS=$(printf "%s" "$RAW_BROKERS" | sed -E 's/[A-Z_]+:\/\///g')

REPLICATION_FACTOR=${REPLICATION_FACTOR:-1}
DOCKER_NETWORK=${DOCKER_NETWORK:-aegis-net}

kt() {
  if command -v kafka-topics >/dev/null 2>&1; then
    kafka-topics "$@"
  elif command -v docker >/dev/null 2>&1; then
    docker run --rm --network "$DOCKER_NETWORK" confluentinc/cp-kafka:7.5.0 kafka-topics "$@"
  else
    echo "kafka-topics not found and docker unavailable." >&2
    exit 1
  fi
}

echo "Waiting for Kafka broker at $BROKERS ..."
for i in $(seq 1 60); do
  if kt --bootstrap-server "$BROKERS" --list >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "Broker not reachable at $BROKERS" >&2
    exit 1
  fi
done

ensure_topic() {
  local topic=$1
  local parts=$2
  local rf=${3:-$REPLICATION_FACTOR}
  echo "Ensuring topic '$topic' (partitions=$parts, rf=$rf)"
  kt --bootstrap-server "$BROKERS" \
     --create --if-not-exists \
     --topic "$topic" \
     --partitions "$parts" \
     --replication-factor "$rf" >/dev/null || true
}

ensure_topic payments 6 1
ensure_topic sms 3 1
ensure_topic email 3 1
ensure_topic alerts 3 1

echo "Topics provisioned."
