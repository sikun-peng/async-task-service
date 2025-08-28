# Async Task Service

A minimal async task queue with retries, compensation, idempotency, and observability.
Built with **FastAPI**, **Postgres**, **Redis**, **RQ**, **Prometheus**, and **Grafana**.

## Features

- **Submit Job** – `POST /v1/jobs { type, payload, idempotencyKey? } → { jobId }`
- **Job Status** – `GET /v1/jobs/{jobId} → { status, attempts, lastError?, startedAt?, completedAt?, result? }`
- **Workers & Queue** – Redis + RQ; fixed-size worker pool (configurable).
- **Retries** – Exponential backoff + jitter; max attempts (configurable).
- **Compensation** – Per job-type `compensate(...)` runs on final failure → `COMPENSATED`.
- **Idempotency** – Same `idempotencyKey` returns the first job.
- **Backpressure** – Bounded queue → returns **429 Too Many Requests** when full.
- **Observability**
  - `/metrics` via `prometheus_fastapi_instrumentator`
  - Custom counters:
    - `api_requests_total` – increments on each `POST /v1/jobs`
    - `jobs_processed_total{status=...}` – increments on terminal status in worker
  - Simple dashboard with Grafana

---

## Architecture (high-level)

```
FastAPI  →  Postgres (job state)
        →  Redis (queue) → RQ Worker → Tasks (retry + compensation)
        →  Prometheus (/metrics) → Grafana
```

---

## Local Dev

### Requirements
- Python 3.11+
- Docker & Docker Compose v2

### One-liner (Docker)
```bash
docker compose up -d --build
```

Services:
- API (FastAPI): `http://localhost:8000`
- OpenAPI/Swagger: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- Redis: `localhost:6379`
- Postgres: `localhost:5432`
- RQ worker(s): background containers consuming Redis queue

---

## Endpoints

- **Health**
  `GET /health` → `{ "status": "ok" }`

- **Submit Job**
  `POST /v1/jobs`
  Body:
  ```json
  { "type": "hash", "payload": { "data": "hello" }, "idempotencyKey": "optional-key" }
  ```
  or
  ```json
  { "type": "block_ip", "payload": { "ip": "192.168.1.1", "reason": "suspicious" } }
  ```
  Response:
  ```json
  { "jobId": "uuid" }
  ```

- **Job Status**
  `GET /v1/jobs/{jobId}
  Response (example):
  ```json
  {
    "id": "uuid",
    "type": "hash",
    "status": "SUCCEEDED",
    "attempts": 1,
    "lastError": null,
    "startedAt": "2025-08-28T00:00:00.000000",
    "completedAt": "2025-08-28T00:00:01.234567",
    "result": { "algo": "sha256", "digest": "..." }
  }
  ```

- **List Jobs**
  `GET /v1/jobs` → most recent first

---

## cURL Quickstart

Submit a `hash` job:
```bash
curl -s -X POST http://localhost:8000/v1/jobs   -H 'Content-Type: application/json'   -d '{"type":"hash","payload":{"data":"hi"}}'
```

Check job status (replace `JOB_ID`):
```bash
curl -s http://localhost:8000/v1/jobs/JOB_ID | jq
```

Submit a `block_ip` job:
```bash
curl -s -X POST http://localhost:8000/v1/jobs   -H 'Content-Type: application/json'   -d '{"type":"block_ip","payload":{"ip":"192.168.1.123","reason":"test"}}'
```

---

## EC2 Deployment Notes

### Running
```bash
git clone https://github.com/sikun-peng/async-task-service.git
cd async-task-service
docker-compose up -d --build
```

Access:
- API: `http://54.188.148.98:8000/docs`
- Prometheus: `http://54.188.148.98:9090`
- Metrics: `http://54.188.148.98:8000/metrics`

### Example against EC2

Submit:
```bash
curl -s -X POST http://54.188.148.98:8000/v1/jobs   -H 'Content-Type: application/json'   -d '{"type":"hash","payload":{"data":"hi"}}'
```

Check metrics:
```bash
curl -s http://54.188.148.98:8000/metrics | grep api_requests_total
```

Run integration tests:
```bash
Change in pytest -q tests/test_integration.py
BASE_URL=http://54.188.148.98:8000 
pytest -q tests/test_integration.py
```



## Grafana Cloud
- Added Grafana dashboard JSON (Prometheus datasource: `async-task-service`)
- link https://sikunpeng.grafana.net/goto/R3nCluXHR?orgId=1
