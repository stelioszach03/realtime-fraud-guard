from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional

import orjson
import redis
from kafka import KafkaProducer

from features.schema import FEATURE_VERSION
from model.registry import load_latest_model
from services.inference_api.settings import get_settings


def _normalize_brokers(raw: str) -> str:
    for scheme in ("PLAINTEXT://", "SASL_PLAINTEXT://", "SASL_SSL://", "SSL://", "kafka://"):
        raw = raw.replace(scheme, "")
    return raw


@lru_cache(maxsize=1)
def _redis_client(url: Optional[str] = None) -> redis.Redis:
    settings = get_settings()
    return redis.from_url(url or settings.REDIS_URL)


@lru_cache(maxsize=1)
def _kafka_producer() -> KafkaProducer:
    settings = get_settings()
    brokers = _normalize_brokers(settings.KAFKA_BROKER)
    return KafkaProducer(
        bootstrap_servers=brokers.split(","),
        value_serializer=lambda v: orjson.dumps(v),
        key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
    )


def write_alert(alert: Dict[str, Any]) -> None:
    """Write alert to Redis Stream 'alerts' (trim to 10k) and Kafka alerts topic.

    Enriches alert with: reasons, model_version, feature_version, source_topic, partition, offset.
    """
    # Enrich with model/feature versions if missing
    if "model_version" not in alert:
        try:
            _, mv, _, _ = load_latest_model()
            alert["model_version"] = mv
        except Exception:
            alert.setdefault("model_version", "none")
    alert.setdefault("feature_version", FEATURE_VERSION)

    # Normalize source/topic metadata
    if "source_topic" not in alert and "source" in alert:
        alert["source_topic"] = alert.get("source")
    alert.setdefault("partition", None)
    alert.setdefault("offset", None)
    alert.setdefault("reasons", [])

    # Push to Redis Stream with MAXLEN ~ 10k
    try:
        rc = _redis_client()
        rc.xadd("alerts", {"data": json.dumps(alert)}, maxlen=10000, approximate=True)
    except Exception:
        pass

    # Publish to Kafka alerts topic
    try:
        settings = get_settings()
        topic = os.getenv("KAFKA_TOPIC_ALERTS", settings.KAFKA_TOPIC_ALERTS)
        prod = _kafka_producer()
        event = alert.get("event", {})
        key = (
            event.get("user_id")
            or event.get("recipient")
            or event.get("phone_number")
            or alert.get("key")
            or "unknown"
        )
        headers = [
            (b"type", b"alert"),
            (b"source", str(alert.get("source_topic", "")).encode()),
            (b"model_version", str(alert.get("model_version", "")).encode()),
            (b"feature_version", str(alert.get("feature_version", "")).encode()),
        ]
        prod.send(topic, key=key, value=alert, headers=headers)
        prod.flush()
    except Exception:
        pass

