from __future__ import annotations

import os
from typing import Any

import orjson
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from model.inference_core import InferenceEngine
from .latency import track_latency
from .schemas import ScoreRequest, ScoreResponse


def orjson_dumps(v: Any, *, default) -> bytes:
    return orjson.dumps(v, default=default)


app = FastAPI(title="Aegis Fraud & Scam Guard")
engine = InferenceEngine()
registry = CollectorRegistry()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": engine.model_version}


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    with track_latency():
        proba, reasons, rule_hits, version = engine.predict_proba_and_reasons(req.event_type, req.event)
    logger.info("score", event_type=req.event_type, risk=proba, reasons=reasons, rules=rule_hits)
    return ScoreResponse(id=req.id, risk_score=proba, reasons=reasons, rule_hits=rule_hits, model_version=version)


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    data = generate_latest()  # default REGISTRY
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)

