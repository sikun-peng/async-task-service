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

### Job Types

The service currently supports **two job types** to demonstrate retries, compensation, and idempotency:

#### 1. Hash Job (`type: "hash"`)
- **Purpose**: Generate a deterministic hash (digest) of an input string or bytes.
- **Execute**: Uses the algorithm (default: `sha256`) to compute a hash of the provided payload.
- **Compensate**: Does nothing meaningful (just returns `{ "compensated": true }`) since hashing is side-effect free.
- **Example**
  ```bash
  curl -s -X POST http://localhost:8000/v1/jobs \
    -H 'Content-Type: application/json' \
    -d '{"type":"hash","payload":{"data":"hello"}}'
  ```
Response:
  ```json
  { "jobId": "uuid" }
  ```
Status result:
  ```json
  {
    "id": "uuid",
    "type": "hash",
    "status": "SUCCEEDED",
    "result": {
      "algo": "sha256",
      "digest": "2cf24dba5fb0..."
    }
  }
````

#### 2. Block IP Job (type: "block_ip")
- **Purpose**: Simulate a side-effectful operation by blocking an IP address.
- **Execute**: Marks the given IP as “blocked” with a reason (policy/suspicious/etc.).
(No actual persistence in this demo — just returns a simulated result.)
- **Compensate**: If execution fails, runs a simulated “unblock” action.
For example, returns { "ip": "192.168.1.123", "unblocked": true }.
- **Example**

  ```bash
  curl -s -X POST http://localhost:8000/v1/jobs \
    -H 'Content-Type: application/json' \
    -d '{"type":"block_ip","payload":{"ip":"192.168.1.123","reason":"suspicious"}}'
  ```
  
Response:
  ```json
  { "jobId": "uuid" }
  ```

Status result:
  ```json
  {
    "id": "uuid",
    "type": "block_ip",
    "status": "SUCCEEDED",
    "result": {
      "ip": "192.168.1.123",
      "blocked": true,
      "reason": "suspicious"
    }
  }
  ```


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

### Swagger UI
![Swagger UI](./docs/EC2%20Swagger.png)
- Link: `http://54.188.148.98:8000/docs`

### Metrics UI
![Prometheus](./docs/EC2%20Metrics.png)
- Link: `http://54.188.148.98:8000/metrics`

### Prometheus Metrics
![Prometheus](./docs/EC2%20Prometheus.png)
- Link: `http://54.188.148.98:9090`

### Example against EC2

Submit:
```bash
curl -s -X POST http://54.188.148.98:8000/v1/jobs   -H 'Content-Type: application/json'   -d '{"type":"hash","payload":{"data":"hi"}}'
```

Check metrics:
```bash
curl -s http://54.188.148.98:8000/metrics | grep api_requests_total
```

To Run integration tests:
```
In tests/test_integration.py
update BASE_URL= "http://54.188.148.98:8000"

Run integration test 
pytest -q tests/test_integration.py
```



## Grafana Cloud

![Grafana Dashboard](./docs/Grafana%20Cloud.png)

- Added Grafana dashboard JSON (Prometheus datasource: `async-task-service`)
- link https://sikunpeng.grafana.net/goto/R3nCluXHR?orgId=1
