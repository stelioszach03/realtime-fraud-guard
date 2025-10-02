from __future__ import annotations

import sys
from loguru import logger


def configure_logging(level: str = "INFO", service: str = "app") -> None:
    logger.remove()
    # JSON structured logs
    logger.add(
        sys.stdout,
        level=level.upper(),
        serialize=True,
        backtrace=False,
        diagnose=False,
        filter=lambda record: record.update({"extra": {**record.get("extra", {}), "service": service}}) or True,
    )
