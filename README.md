# Realtime Fraud Guard

Streaming fraud-detection platform: payments, SMS and email are scored through one decision contract, served synchronously over REST/gRPC and asynchronously through Kafka → consumer → Redis Streams.

[![CI](https://github.com/stelioszach03/realtime-fraud-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/stelioszach03/realtime-fraud-guard/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-22d3ee?style=flat-square)](LICENSE)

## Results

**This is a streaming-systems project, not a model result, and it publishes no accuracy number.**

The classifier is a logistic regression trained and evaluated on a synthetic corpus this repo generates itself ([`evaluation/datasets/synth_v2.jsonl`](evaluation/datasets/synth_v2.jsonl), 3,000 balanced rows). The two classes are separable by construction — a benign SMS reads `"Library book due this week."`, a fraud one reads `"You WON $10,000! Click http://… URGENT."` — so any offline score is a **sanity check that the pipeline is wired end to end**, not evidence that the model detects fraud. `make eval` prints to stdout and nothing is committed, deliberately.

What the repo actually demonstrates:

| Component | Evidence |
|---|---|
| Kafka → scoring consumer → Redis Streams alert topic | [`services/inference_api/kafka_consumer.py`](services/inference_api/kafka_consumer.py), [`docker-compose.yml`](docker-compose.yml) |
| One decision contract across three channels | `POST /score` → `{score, is_alert, threshold, reasons, latency_ms}` |
| gRPC mirror of the same contract | [`protos/fraud.proto`](protos/fraud.proto) — `FraudScoring.Score` |
| Per-channel feature pipelines + rule DSL for reason codes | [`features/`](features/), [`services/rules/`](services/rules/) |
| Prometheus + Grafana dashboards, PSI/JS drift report | [`dashboards/`](dashboards/), `make drift` |

## Run

```bash
cp .env.example .env
make compose-up      # Kafka, Redis, API, consumer, Prometheus, Grafana
make topics          # idempotent topic bootstrap
# API http://localhost:8000/docs · Prom :9090 · Grafana :3000 (admin/admin)
```

Local venv:

```bash
make install
make dev-api          # uvicorn scoring API
make dev-consumer     # Kafka → scorer → Redis Stream
make train            # writes models/<ts>/model.joblib + registry entry
make eval             # PR-AUC / ROC-AUC / precision@k on the synthetic corpus
```

## Limitations

- **The data is synthetic and self-generated**, for both training and evaluation. There is no held-out set from a different distribution and no real-world labels.
- **The classes are trivially separable**, so no metric computed here transfers to real fraud detection. No AUC or accuracy figure from this repo should be quoted as an ML result.
- **Class balance is unrealistic.** Real fraud is heavily imbalanced; a balanced corpus removes the hardest part of the problem.
- **The model is a logistic regression**, deliberately — the engineering is the streaming path and the decision contract, not the classifier.
- **Alerting is fire-and-forget.** Redis Streams has no consumer-group acknowledgement wired up.
- Threshold updates via `PUT /config` are in-memory and reset on restart.

Evaluating on a public labelled dataset (IEEE-CIS, Sparkov) and committing the metrics artifact is the missing piece that would make this an ML result.

## License

MIT — see [LICENSE](LICENSE).
