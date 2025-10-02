from __future__ import annotations

import json
import os
import signal
import threading
import time
from typing import Any, Dict, Iterable, Optional

import orjson
import redis
from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from loguru import logger
from prometheus_client import Counter, Histogram

from model.inference_core import InferenceEngine
from monitoring.exporters.custom_metrics import (
    EVENTS_TOTAL as EVENTS_TOTAL,
    ALERTS_TOTAL as ALERTS_TOTAL,
    INFERENCE_LATENCY_SECONDS as INFERENCE_LATENCY_SECONDS,
    start_metrics_server,
)
from services.inference_api.latency import P95 as P95_LAT
import monitoring.startup_metrics  # noqa: F401  (loads baseline metrics)
from monitoring.logging import configure_logging
from services.inference_api.settings import get_settings
from services.inference_api.alert_sink import write_alert

try:  # leverage existing histogram for p95 tracking as well
    from inference_api.latency import REQUEST_LATENCY as API_LATENCY_HIST
except Exception:  # pragma: no cover
    API_LATENCY_HIST = None


# Metrics are provided by monitoring.exporters.custom_metrics


def _normalize_brokers(raw: str) -> str:
    for scheme in ("PLAINTEXT://", "SASL_PLAINTEXT://", "SASL_SSL://", "SSL://", "kafka://"):
        raw = raw.replace(scheme, "")
    return raw


def _redis_client(url: Optional[str]) -> redis.Redis:
    return redis.from_url(url or "redis://localhost:6379/0")


def _producer(brokers: str) -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=brokers.split(","),
        value_serializer=lambda v: orjson.dumps(v),
        key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
    )


def _consumer(brokers: str, group_id: str, topics: list[str]) -> KafkaConsumer:
    return KafkaConsumer(
        *topics,
        bootstrap_servers=brokers.split(","),
        group_id=group_id,
        enable_auto_commit=False,  # at-least-once
        auto_offset_reset="latest",
        value_deserializer=lambda v: orjson.loads(v),
        consumer_timeout_ms=1000,
        max_poll_records=200,
    )


def _topic_to_source(topic: str) -> str:
    return topic  # topics already named payments|sms|email


def _source_to_event_type(source: str) -> str:
    return {"payments": "payment", "sms": "sms", "email": "email"}.get(source, "payment")


def _publish_alert(
    r: redis.Redis,
    prod: KafkaProducer,
    out_topic: str,
    source: str,
    payload: Dict[str, Any],
    score: float,
    reasons: list[str],
    threshold: float,
    partition: int,
    offset: int,
) -> None:
    alert = {
        "source": source,
        "source_topic": source,
        "event": payload,
        "score": score,
        "threshold": threshold,
        "reasons": reasons,
        "partition": partition,
        "offset": offset,
        "ts": int(time.time() * 1000),
    }
    write_alert(alert)


def run_consumer(stop_event: Optional[threading.Event] = None) -> None:
    settings = get_settings()
    try:
        configure_logging(level=os.getenv("LOG_LEVEL", "INFO"), service="consumer")
    except Exception:
        pass
    brokers = _normalize_brokers(settings.KAFKA_BROKER)
    topics = settings.topics_in_list()
    group_id = settings.KAFKA_GROUP_ID
    threshold = float(os.getenv("SCORE_THRESHOLD", settings.SCORE_THRESHOLD))
    out_topic = os.getenv("KAFKA_TOPIC_ALERTS", settings.KAFKA_TOPIC_ALERTS)

    logger.info(
        "consumer_start brokers={} group={} topics={} out_topic={} threshold={}",
        brokers,
        group_id,
        topics,
        out_topic,
        threshold,
    )

    # Start custom Prometheus metrics server for consumer
    try:
        start_metrics_server(int(getattr(settings, "PROMETHEUS_PORT", 9000)))
    except Exception:
        pass

    r = _redis_client(settings.REDIS_URL)
    prod = _producer(brokers)
    cons = _consumer(brokers, group_id, topics)
    engine = InferenceEngine()

    stop = stop_event or threading.Event()

    try:
        while not stop.is_set():
            polled = cons.poll(timeout_ms=1000)
            if not polled:
                continue
            for tp, records in polled.items():
                for msg in records:
                    start = time.perf_counter()
                    source = _topic_to_source(msg.topic)
                    payload: Dict[str, Any] = msg.value if isinstance(msg.value, dict) else {}
                    EVENTS_TOTAL.labels(topic=source).inc()
                    event_type = _source_to_event_type(source)
                    prob, reasons, latency_ms = engine.score({"event_type": event_type, "event": payload})

                    # Observe latency
                    sec = latency_ms / 1000.0
                    INFERENCE_LATENCY_SECONDS.observe(sec)
                    P95_LAT.observe_seconds(sec)
                    if API_LATENCY_HIST is not None:
                        try:
                            API_LATENCY_HIST.observe(sec)
                        except Exception:
                            pass

                    if prob >= threshold:
                        ALERTS_TOTAL.labels(topic=source).inc()
                        _publish_alert(r, prod, out_topic, source, payload, prob, reasons, threshold, msg.partition, msg.offset)

                    # commit after processing for at-least-once
                    try:
                        cons.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
                    except Exception as e:
                        logger.warning("commit_failed topic={} partition={} offset={} err={}", msg.topic, msg.partition, msg.offset, e)
    except KeyboardInterrupt:
        logger.info("consumer_shutdown keyboard_interrupt")
    finally:
        try:
            prod.flush()
            cons.commit()
        except Exception:
            pass
        try:
            cons.close()
        except Exception:
            pass


def main() -> None:  # pragma: no cover
    stop = threading.Event()

    def _sig_handler(signum, frame):  # noqa: ARG001
        stop.set()

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    run_consumer(stop)


if __name__ == "__main__":  # pragma: no cover
    main()
