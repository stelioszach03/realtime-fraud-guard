from __future__ import annotations

import os
import random
import time
import uuid
from typing import Iterable, Optional

import orjson
from kafka import KafkaProducer

from . import GENERATOR_VERSION
from .profiles import Persona, sample_geo, sample_ip, sample_personas
from .schemas import EmailEvent


LEGIT_SENDERS = ["no-reply@shop.com", "support@bank.com", "newsletter@news.com", "it@corp.com"]
BRANDS = ["ContosoBank", "AcmePay", "ShipIt", "StreamFlix"]
PHISH_TEMPLATES = [
    "{brand} Security Notice: Verify your account immediately",
    "Payment Declined - Update Details",
    "Action required: Password reset",
]


def _normalize_brokers(raw: str) -> str:
    for scheme in ("PLAINTEXT://", "SASL_PLAINTEXT://", "SASL_SSL://", "SSL://", "kafka://"):
        raw = raw.replace(scheme, "")
    return raw


def _get_producer(broker: Optional[str] = None) -> KafkaProducer:
    raw = broker or os.getenv("KAFKA_BROKER") or os.getenv("KAFKA_BROKERS", "localhost:9092")
    brokers = _normalize_brokers(raw)
    return KafkaProducer(
        bootstrap_servers=brokers.split(","),
        value_serializer=lambda v: orjson.dumps(v),
        key_serializer=lambda v: v.encode("utf-8"),
    )


def _rand_phish_sender(brand: str) -> str:
    domains = [
        f"{brand.lower()}-secure.com",
        f"{brand.lower()}-support.net",
        f"{brand.lower()}-verify.com",
    ]
    return f"security@{random.choice(domains)}"


def _gen_email(rng: random.Random, personas: list[Persona], fraud_ratio: float) -> Iterable[dict]:
    while True:
        p = rng.choice(personas)
        is_fraud = rng.random() < fraud_ratio or (p.type == "fraudster" and rng.random() < 0.6)
        brand = rng.choice(BRANDS)
        if is_fraud:
            sender = _rand_phish_sender(brand)
            subject = rng.choice(PHISH_TEMPLATES).format(brand=brand)
            body = f"Dear user, please click http://{brand.lower()}-secure.example/verify to secure your account."
        else:
            sender = rng.choice(LEGIT_SENDERS)
            subject = f"{brand} - Welcome!"
            body = "Your subscription is active. Thank you!"

        country, lat, lon = sample_geo(p.home_country)
        e = EmailEvent(
            event_id=str(uuid.uuid4()),
            user_id=p.user_id,
            device_id=rng.choice(p.devices),
            ip=sample_ip(country),
            country=country,
            city_lat=lat,
            city_lon=lon,
            sender=sender,
            recipient=f"{p.user_id}@example.com",
            subject=subject,
            body=body,
            sender_domain=sender.split("@")[-1],
            is_fraud=is_fraud,
        )
        yield e.model_dump(mode="json")


def run(
    topic: str = "email",
    rate: float = 20.0,
    burst: bool = False,
    fraud_ratio: float = 0.03,
    max_events: Optional[int] = None,
    kafka_broker: Optional[str] = None,
) -> None:
    rng = random.Random()
    personas = sample_personas()
    producer = _get_producer(kafka_broker)
    headers = [("source", b"aegis-generator"), ("version", GENERATOR_VERSION.encode())]
    sent = 0
    gen = _gen_email(rng, personas, fraud_ratio)
    try:
        if burst:
            batch = max(1, int(rate // 10))
            while True:
                for _ in range(batch):
                    payload = next(gen)
                    producer.send(topic, key=payload.get("user_id", "unknown"), value=payload, headers=headers)
                    sent += 1
                    if max_events and sent >= max_events:
                        raise StopIteration
                producer.flush()
                time.sleep(0.1)
        else:
            while True:
                payload = next(gen)
                producer.send(topic, key=payload.get("user_id", "unknown"), value=payload, headers=headers)
                sent += 1
                if max_events and sent >= max_events:
                    break
                sleep_s = random.expovariate(rate) if rate > 0 else 0.5
                time.sleep(sleep_s)
    except StopIteration:
        pass
    finally:
        producer.flush()
        producer.close()
