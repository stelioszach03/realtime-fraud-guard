from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    event_id: str
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    ip: Optional[str] = None
    country: Optional[str] = None
    city_lat: Optional[float] = None
    city_lon: Optional[float] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
    is_fraud: Optional[bool] = Field(default=None, description="Optional label for evaluation")


class PaymentEvent(BaseEvent):
    amount: float
    currency: str
    merchant_id: str
    merchant_name: str
    mcc: int


class SMSEvent(BaseEvent):
    phone_number: str
    message_text: str
    brand: Optional[str] = None


class EmailEvent(BaseEvent):
    sender: str
    recipient: str
    subject: str
    body: str
    sender_domain: Optional[str] = None
