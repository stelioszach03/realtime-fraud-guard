from __future__ import annotations

import json
import os
from typing import Any, Dict

import orjson
import redis
from kafka import KafkaProducer


def _redis_client(url: str | None = None) -> redis.Redis:
    return redis.from_url(url or os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _kafka_producer() -> KafkaProducer:
    brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    return KafkaProducer(bootstrap_servers=brokers.split(","), value_serializer=lambda v: orjson.dumps(v))


def publish_alert(event: Dict[str, Any], score: float, reasons: list[str], rule_hits: list[str]) -> None:
    payload = {
        "event": event,
        "score": score,
        "reasons": reasons,
        "rule_hits": rule_hits,
    }
    # Redis Stream
    rc = _redis_client()
    rc.xadd("fraud_alerts", {"data": json.dumps(payload)})
    # Kafka topic
    producer = _kafka_producer()
    topic = os.getenv("KAFKA_TOPIC_ALERTS", "alerts")
    producer.send(topic, payload)
    producer.flush()
