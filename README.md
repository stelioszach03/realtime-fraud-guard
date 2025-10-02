# Aegis Fraud & Scam Guard (MVP)

Real-time fraud and scam detection across payments, SMS, and email. This MVP includes synthetic data generators, rolling features, a rules DSL, model training/inference, REST/gRPC APIs, and monitoring.

## Architecture

```
             +-------------------+
             |  Generators       |
             | payments/sms/email|
             +---------+---------+
                       |
                       v
                 +-----+-----+           +-------------------------+
                 |   Kafka    +--------->+   Consumer (scoring)    |
                 +-----+-----+           |  model + rules + alerts |
                       ^                 +------+------------------+
                       |                        |
        +--------------+--+                     v
        |    REST/gRPC API |             +------+------+
        | (sync scoring)   |             |  Redis      |  Kafka alerts
        +---------+--------+             |  Stream     +-------------->
                  |                      +------+------+              
                  v                             |                     
            +-----+------+                     v                     
            | Prometheus | <------------- custom/HTTP metrics         
            +-----+------+                                              
                  |                                                     
                  v                                                     
            +-----+------+                                              
            |  Grafana   |  Dashboards: overview, drift, alerts        
            +------------+                                              
```

Demo flow: generator -> kafka -> consumer/api -> alerts -> grafana.

## Endpoints (REST)
- GET `/health` → status, version, env, model_version
- POST `/score` → `{score, is_alert, threshold, reasons, latency_ms}`
- GET `/metrics` → Prometheus exposition
- GET `/config` → `{threshold, topics_in, model_version, model_meta}`
- PUT `/config` → update `threshold` (MVP in-memory)

gRPC mirrors the same scoring contract: `FraudScoring.Score`.

## How To Run

Using Docker Compose (recommended):
- Copy env and launch stack:
```
cp .env.example .env
make compose-up
```
- Bootstrap topics (idempotent): `make topics`
- Open Grafana: http://localhost:3000 (admin/admin)

Local dev (venv):
- Install deps: `make install`
- Run API: `make dev-api`
- Run consumer: `make dev-consumer`

Training / Evaluation:
- Train baseline models and save to `models/`:
```
make train
```
- Offline evaluation (PR-AUC, ROC-AUC, precision@k):
```
make eval
```
- Drift report (PSI + JS):
```
make drift
```

## Metrics Explained
- PR-AUC: area under precision–recall; robust for imbalanced labels
- precision@k: precision of top-k scores (e.g., 100/500/1000)
- p95/p99 latency: 95th/99th percentile of end-to-end scoring latency
- drift_score: aggregate of normalized PSI and JS divergence across features

## Repo Layout
- services/generator: Synthetic event producers (Kafka)
- features: Rolling/time-window features and featurization
- model: Training, registry, inference with explanations
- services/rules: Rule DSL and human-readable reasons
- services/inference_api: REST, gRPC, consumer, latency, settings, schemas
- dashboards: Prometheus + Grafana provisioning
- monitoring: Custom metrics exporter helpers
- evaluation: Offline evaluation and drift detection
- scripts: Topic bootstrap and dataset loader
- tests: Unit tests for features, rules, inference, API

## Roadmap
- Go high-perf consumer (shared-nothing worker pool)
- Flink/Spark streaming integration and stateful windows
- Feature store (online/offline) with backfill
- Canary model deploy + shadow evaluation

<!--RESULTS:START-->

## Results

**Health**
```json
{"status":"ok","app":"Aegis Fraud Guard","version":"0.1.0","env":"dev","model_version":"bootstrap-1757352963"}
```

**Ready**

```json
{"ready":true,"model":true,"kafka":true}
```

**Latency**

```json
{"p95_seconds":0.05}
```

**Test Summary**
```
.......                                                                  [100%]
=============================== warnings summary ===============================
services/inference_api/main.py:44
  /app/services/inference_api/main.py:44: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

../usr/local/lib/python3.11/site-packages/fastapi/applications.py:4495
  /usr/local/lib/python3.11/site-packages/fastapi/applications.py:4495: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
7 passed, 2 warnings in 2.29s
```

**Offline Metrics**

| Metric         | Value |
| -------------- | ----- |
| PR-AUC         | 0.8667 |
| ROC-AUC        | 0.6667 |
| precision@100  | 0.6000 |
| precision@500  | 0.6000 |

**Drift**

- drift_score: 0.1773

**Sample Scoring Outputs**

```json
// payments
{"score":0.8918722062166436,"is_alert":true,"threshold":0.85,"reasons":["amount","merchant_risk","txn_count_1m_user"],"latency_ms":1.2028470009681769}
```

```json
// sms
{"score":0.004435815526308063,"is_alert":false,"threshold":0.85,"reasons":["text_len","url_count","suspicious_word_hits"],"latency_ms":0.8185109982150607}
```

```json
// email
{"score":0.002900473729080121,"is_alert":false,"threshold":0.85,"reasons":["subject_len","body_len","link_count"],"latency_ms":0.7288939996215049}
```

**Topics Created**

- payments (6 partitions)
- sms (3 partitions)
- email (3 partitions)
- alerts (3 partitions)

**URLs**

- REST: http://localhost:8000
- Ready: http://localhost:8000/ready
- Latency: http://localhost:8000/latency
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- gRPC: localhost:50051

<!--RESULTS:END-->
