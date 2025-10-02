from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "Aegis Fraud Guard"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "dev"  # dev | staging | prod

    # Kafka
    KAFKA_BROKER: str = "PLAINTEXT://redpanda:9092"
    # Store as string to avoid JSON decoding errors when coming from env
    KAFKA_TOPICS_IN: str = "payments,sms,email"  # CSV in env
    KAFKA_TOPIC_ALERTS: str = "alerts"
    KAFKA_GROUP_ID: str = "fraud-inference"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Prometheus (exporter)
    PROMETHEUS_PORT: int = 9000

    # Model
    MODEL_DIR: str = "/models"
    MODEL_NAME: str = "fraud_xgb.json"

    # Inference behavior
    SCORE_THRESHOLD: float = 0.85
    TOP_K_EXPLANATIONS: int = 3
    MAX_QUEUE_BACKLOG: int = 10000

    def topics_in_list(self) -> List[str]:
        v = self.KAFKA_TOPICS_IN
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, list):
            return v
        return ["payments", "sms", "email"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
