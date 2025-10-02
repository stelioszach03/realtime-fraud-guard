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
from .schemas import SMSEvent


PHISH_PATTERNS = [
    "Urgent! Verify your bank password at {url}",
    "Your package is on hold, pay fee at {url}",
    "We noticed unusual activity, secure your account: {url}",
]

BRANDS = ["ContosoBank", "AcmePay", "ShipIt", "StreamFlix"]
SHORTENERS = ["bit.ly/", "tinyurl.com/", "goo.gl/"]


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


def _rand_url(rng: random.Random) -> str:
    short = rng.choice(SHORTENERS) + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(7))
    return f"http://{short}"


def _gen_sms(rng: random.Random, personas: list[Persona], fraud_ratio: float) -> Iterable[dict]:
    while True:
        p = rng.choice(personas)
        is_fraud = rng.random() < fraud_ratio or p.type == "fraudster" and rng.random() < 0.5
        brand = rng.choice(BRANDS)
        url = _rand_url(rng)
        if is_fraud:
            msg = rng.choice(PHISH_PATTERNS).format(url=url)
        else:
            msg = f"{brand}: Your OTP is {rng.randint(100000, 999999)}. Do not share."
        country, lat, lon = sample_geo(p.home_country)
        e = SMSEvent(
            event_id=str(uuid.uuid4()),
            user_id=p.user_id,
            device_id=rng.choice(p.devices),
            ip=sample_ip(p.home_country),
            country=country,
            city_lat=lat,
            city_lon=lon,
            phone_number=f"+1{rng.randint(2000000000, 9999999999)}",
            message_text=msg,
            brand=brand if not is_fraud else rng.choice([brand, f"{brand}-Secure", f"{brand}-Support"]),
            is_fraud=is_fraud,
        )
        yield e.model_dump(mode="json")


def run(
    topic: str = "sms",
    rate: float = 50.0,
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
    gen = _gen_sms(rng, personas, fraud_ratio)
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
