from __future__ import annotations

import json
import os
from typing import Dict

from kafka import KafkaConsumer

from model.inference_core import InferenceEngine
from .alert_sink import publish_alert


def run_stream_scoring(group_id: str = "inference-group", topics: list[str] | None = None, alert_threshold: float = 0.85) -> None:
    topics = topics or ["payments", "sms", "email"]
    brokers = os.getenv("KAFKA_BROKERS", "localhost:9092").split(",")
    consumer = KafkaConsumer(
        *topics,
        bootstrap_servers=brokers,
        group_id=group_id,
        auto_offset_reset="latest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    engine = InferenceEngine()
    for msg in consumer:
        event_type = {
            "payments": "payment",
            "sms": "sms",
            "email": "email",
        }.get(msg.topic, "payment")
        event: Dict = msg.value
        score, reasons, rule_hits, _ = engine.predict_proba_and_reasons(event_type, event)
        if score >= alert_threshold:
            publish_alert(event, score, reasons, rule_hits)


if __name__ == "__main__":
    run_stream_scoring()

