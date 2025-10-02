#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import Dict, List

import orjson
from kafka import KafkaProducer


TOPICS = ["payments", "sms", "email"]
TARGET_PER_TOPIC = 1000
SAMPLE_PATH = Path("evaluation/datasets/sample.jsonl")


def _normalize_brokers(raw: str) -> str:
    # remove common schemes e.g., PLAINTEXT://, SASL_SSL://
    for scheme in ("PLAINTEXT://", "SASL_PLAINTEXT://", "SASL_SSL://", "SSL://", "kafka://"):
        raw = raw.replace(scheme, "")
    return raw


def _producer() -> KafkaProducer:
    raw = os.getenv("KAFKA_BROKER") or os.getenv("KAFKA_BROKERS", "localhost:9092")
    brokers = _normalize_brokers(raw)
    return KafkaProducer(bootstrap_servers=brokers.split(","), value_serializer=lambda v: orjson.dumps(v))


def _rand_payment() -> Dict:
    return {
        "event_id": str(uuid.uuid4()),
        "user_id": f"u_{random.randint(1, 500)}",
        "device_id": f"d_{random.randint(1, 1000)}",
        "merchant": random.choice(["ACME-MARKET", "GLOBAL-TRAVEL", "MEGASTORE", "STREAMFLIX"]),
        "amount": round(max(1.0, random.gauss(75, 50)), 2),
        "currency": "USD",
        "country": random.choice(["US", "GB", "DE", "IN", "CA"]),
    }


def _rand_sms() -> Dict:
    suspicious = random.random() < 0.3
    text = (
        "Urgent! Verify your bank password at http://phish"
        if suspicious
        else f"Hello user, your OTP is {random.randint(100000, 999999)}"
    )
    return {
        "event_id": str(uuid.uuid4()),
        "phone_number": f"+1{random.randint(2000000000, 9999999999)}",
        "text": text,
        "country": "US",
    }


def _rand_email() -> Dict:
    phishing = random.random() < 0.25
    sender = random.choice(["no-reply@shop.com", "support@bank.com", "newsletter@news.com", "it@corp.com"]) if not phishing else random.choice(["security@bank-secure.com", "verify@pay-service.net"]) 
    subject = "Verify your password immediately" if phishing else "Welcome to our service"
    body = (
        "Please click http://malicious.link to secure your account"
        if phishing
        else "Your subscription is active. Thank you!"
    )
    return {
        "event_id": str(uuid.uuid4()),
        "sender": sender,
        "recipient": f"user{random.randint(1,9999)}@example.com",
        "subject": subject,
        "body": body,
        "sender_domain": sender.split("@")[-1],
    }


def _load_samples() -> Dict[str, List[Dict]]:
    samples: Dict[str, List[Dict]] = {"payment": [], "sms": [], "email": []}
    if not SAMPLE_PATH.exists():
        return samples
    with SAMPLE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            et = row.get("event_type", "")
            ev = row.get("event", {})
            if et in samples:
                samples[et].append(ev)
    return samples


def main() -> None:
    prod = _producer()
    samples = _load_samples()

    topic_map = {"payments": "payment", "sms": "sms", "email": "email"}
    gen_map = {"payments": _rand_payment, "sms": _rand_sms, "email": _rand_email}

    for topic in TOPICS:
        et = topic_map[topic]
        pool = samples.get(et, [])
        total = 0
        while total < TARGET_PER_TOPIC:
            if pool:
                ev = pool[total % len(pool)]
            else:
                ev = gen_map[topic]()
            prod.send(topic, ev)
            total += 1
            if total % 200 == 0:
                prod.flush()
        prod.flush()
        print(f"Produced {total} messages to {topic}")

    print("Done loading sample/random dataset to topics.")


if __name__ == "__main__":
    main()
