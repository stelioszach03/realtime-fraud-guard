from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ScoreRequest(BaseModel):
    source: str = Field(pattern=r"^(payments|sms|email)$")
    payload: Dict[str, Any]


class ScoreResponse(BaseModel):
    score: float
    is_alert: bool
    threshold: float
    reasons: List[str] = []
    latency_ms: float


class ConfigResponse(BaseModel):
    threshold: float
    topics_in: List[str]
    model_version: str | None = None
    model_meta: Dict[str, Any] = {}


class ConfigUpdate(BaseModel):
    threshold: float

