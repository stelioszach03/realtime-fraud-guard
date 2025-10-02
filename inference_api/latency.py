from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import Histogram


REQUEST_LATENCY = Histogram(
    "inference_request_latency_seconds",
    "Latency for /score requests",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)


@contextmanager
def track_latency():
    start = time.perf_counter()
    try:
        yield
    finally:
        REQUEST_LATENCY.observe(time.perf_counter() - start)

