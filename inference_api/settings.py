from __future__ import annotations

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    kafka_brokers: str = os.getenv("KAFKA_BROKERS", "localhost:9092")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    model_dir: str = os.getenv("MODEL_DIR", "./models")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    service_name: str = os.getenv("SERVICE_NAME", "inference_api")


settings = Settings()

