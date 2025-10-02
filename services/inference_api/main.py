from __future__ import annotations

import os
import time
from typing import Any

import orjson
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse, PlainTextResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest
from monitoring.exporters.custom_metrics import start_metrics_server
from services.inference_api.latency import P95 as P95_LAT
import monitoring.startup_metrics  # noqa: F401  (loads metrics at import)
from monitoring.logging import configure_logging
from kafka import KafkaProducer

from model.inference_core import InferenceEngine
from model.registry import save_model_bundle, latest_model_path
from features.featurizer import featurize
from .schemas import ConfigResponse, ConfigUpdate, ScoreRequest, ScoreResponse
from .settings import get_settings


def _orjson_dumps(v: Any, *, default):
    return orjson.dumps(v, default=default)


app = FastAPI(title="Aegis Fraud Guard (services)", default_response_class=ORJSONResponse)
settings = get_settings()
engine = InferenceEngine()

# In-memory (mutable) threshold for MVP
CURRENT_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", settings.SCORE_THRESHOLD))

# Prometheus histogram for latency
SCORE_LATENCY = Histogram(
    "score_request_latency_seconds",
    "Latency for score requests",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)


@app.on_event("startup")
def _startup() -> None:
    global engine
    configure_logging(level=os.getenv("LOG_LEVEL", "INFO"), service="api")
    # If no model present, train a tiny bootstrap model so scoring works
    try:
        if engine.model is None and latest_model_path() is None:
            _bootstrap_minimal_model()
            engine = InferenceEngine()
            logger.info("bootstrap_model_trained version={}", engine.model_version)
    except Exception as e:
        logger.warning("bootstrap_model_failed error={}", e)
    try:
        start_metrics_server(int(os.getenv("PROMETHEUS_PORT", "9000")))
    except Exception:
        pass
    logger.info("service_start app={} env={} version={} model_version={} threshold={}", settings.APP_NAME, settings.APP_ENV, settings.APP_VERSION, engine.model_version, CURRENT_THRESHOLD)


def _ensure_feature_space(examples: list[tuple[list[float], list[str]]]) -> tuple[list[list[float]], list[str]]:
    name_to_idx: dict[str, int] = {}
    X_rows: list[list[float]] = []
    for vec, names in examples:
        for n in names:
            if n not in name_to_idx:
                name_to_idx[n] = len(name_to_idx)
                for row in X_rows:
                    row.append(0.0)
        row = [0.0] * len(name_to_idx)
        for v, n in zip(vec, names):
            row[name_to_idx[n]] = float(v)
        X_rows.append(row)
    feature_names = [None] * len(name_to_idx)
    for n, i in name_to_idx.items():
        feature_names[i] = n
    return X_rows, feature_names  # type: ignore


def _bootstrap_minimal_model() -> None:
    import random
    import time as _t
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    # Generate small synthetic labeled set across sources
    examples: list[tuple[list[float], list[str]]] = []
    labels: list[int] = []

    rng = random.Random(42)
    # payments
    for i in range(200):
        amt = max(1.0, rng.gauss(75, 50))
        ev = {"amount": amt, "merchant_name": rng.choice(["ACME", "GLOBAL-TRAVEL", "MEGASTORE"]), "user_id": f"u{i}"}
        vec, names = featurize("payment", ev)
        examples.append((vec, names))
        labels.append(1 if amt > 300 or rng.random() < 0.1 else 0)
    # sms
    for i in range(150):
        linky = rng.random() < 0.3
        text = "Urgent! Verify your bank password at http://x" if linky else "Your OTP is 123456"
        ev = {"message_text": text, "user_id": f"s{i}"}
        vec, names = featurize("sms", ev)
        examples.append((vec, names))
        labels.append(1 if linky else 0)
    # email
    for i in range(150):
        phish = rng.random() < 0.25
        ev = {
            "subject": "Verify your password" if phish else "Welcome",
            "body": "Click http://y to reset" if phish else "Hello",
            "sender_domain": "bank-secure.com" if phish else "news.com",
            "user_id": f"e{i}",
        }
        vec, names = featurize("email", ev)
        examples.append((vec, names))
        labels.append(1 if phish else 0)

    X_rows, feature_names = _ensure_feature_space(examples)
    X = np.array(X_rows, dtype=float)
    y = np.array(labels, dtype=int)

    pipe = Pipeline([
        ("scaler", StandardScaler(with_mean=False)),
        ("clf", LogisticRegression(max_iter=300)),
    ])
    pipe.fit(X, y)
    version = f"bootstrap-{int(_t.time())}"
    save_model_bundle(pipe, feature_names, version, meta={"model_type": "logreg", "bootstrap": True})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "model_version": engine.model_version,
    }


def get_current_threshold() -> float:
    return CURRENT_THRESHOLD


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    start = time.perf_counter()
    # Normalize mapping: source -> event_type expected by model engine
    event_type = {"payments": "payment", "sms": "sms", "email": "email"}[req.source]
    prob, reasons, _lat_ms = engine.score({"event_type": event_type, "event": req.payload})
    latency_ms = (time.perf_counter() - start) * 1000.0
    SCORE_LATENCY.observe(latency_ms / 1000.0)
    P95_LAT.observe_ms(latency_ms)
    is_alert = bool(prob >= CURRENT_THRESHOLD)
    logger.info("score source={} prob={:.4f} is_alert={} reasons={}", req.source, prob, is_alert, reasons)
    return ScoreResponse(score=prob, is_alert=is_alert, threshold=CURRENT_THRESHOLD, reasons=reasons, latency_ms=latency_ms)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    data = generate_latest()
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


_last_kafka_check_ts: float = 0.0
_last_kafka_ok: bool = False


def _kafka_ready() -> bool:
    import time as _t
    global _last_kafka_check_ts, _last_kafka_ok
    if _t.time() - _last_kafka_check_ts < 30.0:
        return _last_kafka_ok
    try:
        prod = KafkaProducer(bootstrap_servers=settings.KAFKA_BROKER.replace("PLAINTEXT://", ""))
        # request metadata
        prod.partitions_for("payments")
        prod.close()
        _last_kafka_ok = True
    except Exception:
        _last_kafka_ok = False
    _last_kafka_check_ts = _t.time()
    return _last_kafka_ok


@app.get("/ready")
def ready() -> dict:
    ok = (engine.model is not None) and _kafka_ready()
    return {"ready": ok, "model": engine.model is not None, "kafka": _kafka_ready()}


@app.get("/latency")
def latency_snapshot() -> dict:
    return {"p95_seconds": P95_LAT.current_seconds()}


@app.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    meta = engine.meta if getattr(engine, "meta", None) is not None else {}
    return ConfigResponse(
        threshold=CURRENT_THRESHOLD,
        topics_in=settings.topics_in_list(),
        model_version=engine.model_version,
        model_meta=meta,
    )


@app.put("/config", response_model=ConfigResponse)
def put_config(update: ConfigUpdate) -> ConfigResponse:
    global CURRENT_THRESHOLD
    CURRENT_THRESHOLD = float(update.threshold)
    return get_config()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("API_HOST", "0.0.0.0"), port=int(os.getenv("API_PORT", "8000")))
