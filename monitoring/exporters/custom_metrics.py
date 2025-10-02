from __future__ import annotations

from typing import Union

from prometheus_client import Counter, Gauge, Histogram, start_http_server


# Centralized metrics registry for the project

# Counters
EVENTS_TOTAL = Counter("events_total", "Total events processed by topic", ["topic"])  # noqa: E305
ALERTS_TOTAL = Counter("alerts_total", "Total alerts produced by topic", ["topic"])  # noqa: E305

# Latency histogram
INFERENCE_LATENCY_SECONDS = Histogram(
    "inference_latency_seconds",
    "End-to-end inference latency",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# Offline/periodic evaluation Gauges
PR_AUC = Gauge("pr_auc", "Precision-Recall AUC (offline/periodic)")
PRECISION_AT_K = Gauge("precision_at_k", "Precision@k (offline/periodic)", ["k"])
DRIFT_SCORE = Gauge("drift_score", "Feature drift score (PSI/JS)")


def start_metrics_server(port: int) -> None:
    """Start a Prometheus metrics HTTP server on the given port."""
    start_http_server(port)


def update_pr_auc(value: float) -> None:
    PR_AUC.set(value)


def update_precision_at_k(k: Union[int, str], value: float) -> None:
    PRECISION_AT_K.labels(k=str(k)).set(value)


def update_drift_score(value: float) -> None:
    DRIFT_SCORE.set(value)
