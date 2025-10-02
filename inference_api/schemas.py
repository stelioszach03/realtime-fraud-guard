from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScoreRequest(BaseModel):
    event_type: str
    event: Dict[str, Any]
    id: Optional[str] = Field(default=None, description="Optional event id")


class ScoreResponse(BaseModel):
    id: Optional[str] = None
    risk_score: float
    reasons: List[str] = []
    rule_hits: List[str] = []
    model_version: str

