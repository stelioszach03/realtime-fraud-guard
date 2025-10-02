from __future__ import annotations

import os
import random
import time
import uuid
from typing import Iterable, Optional

import orjson
from kafka import KafkaProducer

from . import GENERATOR_VERSION
from .profiles import MERCHANTS, Persona, sample_geo, sample_ip, sample_personas
from .schemas import PaymentEvent


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


def _sample_amount(rng: random.Random, persona: Persona, is_fraud: bool) -> float:
    # Normal: log-normal-ish via exp of gaussian
    base = max(1.0, rng.lognormvariate(4.0, 0.5))  # median ~ e^4 ~= 54.6
    if persona.type == "traveler":
        base *= rng.uniform(0.8, 1.5)
    if is_fraud:
        base *= rng.uniform(2.0, 5.0)
    return round(base, 2)


def _choose_merchant(rng: random.Random):
    return rng.choice(MERCHANTS)


def _gen_payment_events(
    rng: random.Random,
    personas: list[Persona],
    fraud_ratio: float,
) -> Iterable[dict]:
    while True:
        persona = rng.choice(personas)
        is_fraud = rng.random() < fraud_ratio or persona.type == "fraudster" and rng.random() < 0.5
        # Geo drift: normal near home; traveler often elsewhere; fraudster often mismatched
        if persona.type == "normal" and not is_fraud:
            country = persona.home_country
        elif persona.type == "traveler" and not is_fraud:
            country = rng.choice(list({p.home_country for p in personas})) if rng.random() < 0.4 else persona.home_country
        else:
            # fraud drift
            country = rng.choice([c for c in {p.home_country for p in personas} if c != persona.home_country])
        country, lat, lon = sample_geo(country)
        ip = sample_ip(country)

        merchant = _choose_merchant(rng)
        amount = _sample_amount(rng, persona, is_fraud)

        event = PaymentEvent(
            event_id=str(uuid.uuid4()),
            user_id=persona.user_id,
            device_id=rng.choice(persona.devices),
            ip=ip,
            country=country,
            city_lat=lat,
            city_lon=lon,
            amount=amount,
            currency=persona.home_currency,
            merchant_id=merchant.merchant_id,
            merchant_name=merchant.name,
            mcc=merchant.mcc,
            is_fraud=is_fraud,
        )
        yield event.model_dump(mode="json")


def run(
    topic: str = "payments",
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
    try:
        gen = _gen_payment_events(rng, personas, fraud_ratio)
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
            # Poisson process: exponential inter-arrival with lambda=rate (events/sec)
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
