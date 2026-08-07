<div align="center">

[![CI](https://github.com/stelioszach03/realtime-fraud-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/stelioszach03/realtime-fraud-guard/actions)

# Realtime Fraud Guard

**Streaming fraud-detection platform that scores payments, SMS and email in real time — one model family, one decision contract, a SOC console on top.**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Redis](https://img.shields.io/badge/Redis-Streams-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)](https://grafana.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22d3ee?style=flat-square)](LICENSE)

**[Live Landing](https://stelioszach.com/realtime-fraud-guard/)**  ·  **[Interactive Scoring Widget](https://stelioszach.com/realtime-fraud-guard/#live-score)**  ·  **[API Docs](https://stelioszach.com/realtime-fraud-guard/live/docs)**  ·  **[Prometheus](https://stelioszach.com/realtime-fraud-guard/metrics)**

</div>

---

## What it does

Every incoming event — a card transaction, an SMS, or an email — is fed
through a channel-specific **feature pipeline**, a small **rule DSL** for
human-readable reasons, and a **logistic-regression model** trained on a
balanced 3 000-row synthetic corpus. The service returns a score in
`[0, 1]`, an `is_alert` boolean against a tunable threshold, a ranked
`reasons[]` list, and an end-to-end `latency_ms` — all in the same
contract regardless of source.

Upstream, a Kafka ⇢ Consumer topology turns the same model into a streaming
scorer that pushes alerts to a Redis Stream. Downstream, Prometheus + Grafana
dashboards watch throughput, latency, and drift.

> **This is a streaming-systems project, not a model result.** The classifier is
> trained and evaluated on a synthetic corpus this repo generates itself
> ([`evaluation/datasets/synth_v2.jsonl`](evaluation/datasets/synth_v2.jsonl),
> 3 000 balanced rows). The two classes are separable by construction — benign
> SMS reads `"Library book due this week."`, fraud reads
> `"You WON $10,000! Click http://… URGENT."` — so the offline scores are a
> **sanity check that the pipeline is wired end to end**, not evidence that the
> model detects real fraud. **No accuracy or AUC number from this repo should be
> read as an ML result.** The work worth looking at is the transport:
> Kafka → consumer → Redis Streams → Prometheus, one decision contract across
> three channels.

---

## Live demo

Try the scoring widget on the landing — the **"Score live"** section fires
real `POST /score` calls against the deployed API. Flip between payments /
SMS / email, pick the safe or fraud preset, and watch the gauge + reason
chips update live.

Or hit the API from the terminal:

```bash
# safe payment
curl -sS -X POST https://stelioszach.com/realtime-fraud-guard/live/score \
  -H 'content-type: application/json' \
  -d '{"source":"payments",
       "payload":{"amount":25.4,"currency":"USD","user_id":"u_100",
                  "device_id":"d_10","merchant":"LOCAL-CAFE",
                  "merchant_id":"m_cafe","country":"US"}}'
# → {"score":0.008,"is_alert":false,"threshold":0.85,
#     "reasons":["amount","merchant_risk","txn_count_1m_user"],"latency_ms":1.0}

# textbook fraud
curl -sS -X POST https://stelioszach.com/realtime-fraud-guard/live/score \
  -H 'content-type: application/json' \
  -d '{"source":"payments",
       "payload":{"amount":8500,"currency":"USD","user_id":"u_99",
                  "device_id":"d_new","merchant":"CRYPTO-XCHG",
                  "merchant_id":"m_crypto","country":"NG"}}'
# → {"score":0.9999,"is_alert":true,...}
```

---

## Architecture

```
             +-------------------+
             |   Generators      |
             | payments/sms/email|
             +---------+---------+
                       │
                       ▼
                 +-----+-----+           +-------------------------+
                 |   Kafka    +--------->|   Consumer (scoring)    |
                 +-----+-----+           |   model + rules         |
                       ▲                 +------+------------------+
                       │                        │
       +---------------┴----+                   ▼
       |   REST / gRPC API  |             +----+-----+
       |   (sync scoring)   |             |  Redis   |  alerts stream
       +----------+---------+             | Stream   +----------------▶
                  │                        +----+-----+
                  ▼                             │
           +------+------+                      ▼
           |  Prometheus  | ◀─────────── custom HTTP metrics
           +------+------+
                  │
                  ▼
           +------+------+
           |   Grafana    |   Dashboards: overview · drift · alerts
           +-------------+
```

---

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| `POST` | `/score` | `{score, is_alert, threshold, reasons, latency_ms}` |
| `GET`  | `/health` | `{status, version, env, model_version}` |
| `GET`  | `/ready` | readiness on model + Kafka |
| `GET`  | `/latency` | `{p95_seconds}` |
| `GET`  | `/metrics` | Prometheus exposition |
| `GET`  | `/config` | current scoring config |
| `PUT`  | `/config` | update `threshold` (MVP: in-memory) |

gRPC mirrors the scoring contract as `FraudScoring.Score`.

---

## Quickstart

### Docker Compose

```bash
cp .env.example .env
make compose-up      # brings up Kafka, Redis, API, consumer, Prometheus, Grafana
make topics          # idempotent Kafka topic bootstrap

# Grafana → http://localhost:3000  (admin / admin)
# Prom    → http://localhost:9090
# API     → http://localhost:8000/docs
```

### Local (venv)

```bash
make install
make dev-api          # uvicorn scoring API
make dev-consumer     # Kafka → scorer → Redis Stream
```

### Train + evaluate

```bash
make train            # writes models/<ts>/model.joblib + registry entry
make eval             # PR-AUC, ROC-AUC, precision@k — on the synthetic corpus
make drift            # PSI + JS divergence report
```

`make eval` prints to stdout; no evaluation output is committed to this repo.

---

## Feature pipelines

- **Payments** — amount z-score, merchant risk, country risk, device age,
  txn-count-1m per user / device.
- **SMS** — text length, url count, suspicious-word hits, user send rate.
- **Email** — subject / body length, link count, sender-domain TLD risk.

The rules DSL turns activated feature contributions into a short
`reasons[]` list so investigators see *why* an event got its score, not just
the number.

---

## Metrics cheat sheet

| Metric | Meaning |
| --- | --- |
| `PR-AUC` | Precision-recall AUC; robust under class imbalance. |
| `ROC-AUC` | Receiver-operating AUC; comparative, label-balanced. |
| `precision@k` | Precision of the top-k scored events. |
| `p95/p99 latency` | End-to-end scoring latency percentiles. |
| `drift_score` | Normalised PSI + JS across features vs. training baseline. |

---

## Repository layout

| Path | Contents |
| --- | --- |
| `services/generator/` | Synthetic Kafka producers for payments / sms / email. |
| `features/` | Rolling features + featurizer. |
| `model/` | Training, registry, inference engine with explanations. |
| `services/rules/` | Rule DSL and reason-code generation. |
| `services/inference_api/` | REST, gRPC, Kafka consumer, latency, settings. |
| `dashboards/` | Prometheus + Grafana provisioning. |
| `monitoring/` | Custom metrics exporters. |
| `evaluation/` | Offline eval + drift detection scripts. |
| `scripts/` | Topic bootstrap, dataset loader. |
| `tests/` | Unit + API tests. |

---

## Limitations

- **The data is synthetic and self-generated.** Both training and evaluation use
  `evaluation/datasets/synth_v2.jsonl` (3 000 balanced rows). There is no
  held-out set from a different distribution and no real-world labels.
- **The model is a logistic regression**, deliberately. The engineering here is
  the streaming path and the decision contract, not the classifier.
- **Class balance is unrealistic.** Real fraud is heavily imbalanced; a balanced
  corpus removes the hardest part of the problem.
- **The benchmark numbers that exist are latency, not quality.** Nothing in this
  repo measures detection performance on real traffic.
- **Alerting is fire-and-forget.** Redis Streams has no consumer-group
  acknowledgement wired up yet.

---

## Roadmap

- Evaluate on a public labelled dataset (IEEE-CIS, Sparkov) and commit the
  metrics artifact — the missing piece that would make this an ML result.
- Go high-performance consumer (shared-nothing worker pool).
- Flink / Spark Structured Streaming with stateful windows.
- Online/offline feature store with backfill.
- Canary model deploy + shadow-evaluation pipeline.

---

## License

MIT — see [LICENSE](LICENSE).

---

Built in Athens by **Stelios Zacharioudakis** · <sdi2200243@di.uoa.gr> ·
[stelioszach.com](https://stelioszach.com)
