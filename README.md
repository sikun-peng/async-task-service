# Async Task Service

A minimal async job queue with retries, compensation, metrics, and idempotency.  

## Features
- **Job submission**: `POST /v1/jobs { type, payload, idempotencyKey? }` → returns `jobId`.
- **Job status**: `GET /v1/jobs/{jobId}` → status, attempts, errors, timestamps.
- **Job list**: `GET /v1/jobs` → list of recent jobs (newest first).
- **Retries**: Exponential backoff with jitter (`retry.py`), configurable via `.env`.
- **Compensation**: Runs compensating action if job ultimately fails.
- **Idempotency**: Duplicate submissions (same `idempotencyKey`) return the same job.
- **Backpressure**: Bounded queue (RQ).
- **Observability**: 
  - Prometheus metrics at `/metrics` (via `prometheus-fastapi-instrumentator`)
  - Grafana dashboard (compose file includes Prometheus + Grafana stack).

## Endpoints
- `POST /v1/jobs`  
  Submit a job. Example payloads:
  ```json
  { "type": "hash", "payload": { "data": "abc", "algo": "sha256" } }
  { "type": "hash", "payload": { "fail": true } }
  { "type": "block_ip", "payload": { "ip": "1.2.3.4", "reason": "test" } }
  ```
- `GET /v1/jobs/{id}`
- `GET /v1/jobs`
- `GET /metrics`  

## Job Types
- **hash**: Computes a digest of given data (supports `fail: true` to simulate errors).
- **block_ip**: Inserts/removes IPs in the DB.

## Running locally
### Prerequisites
- Docker + docker-compose
- Python 3.9+ (for running tests)

### Run services
```sh
docker-compose up --build
```

This starts:
- `tasksvc_app`: FastAPI service on [http://localhost:8000](http://localhost:8000)
- `tasksvc_worker`: RQ worker
- `redis`: Redis backend
- `prometheus`: [http://localhost:9090](http://localhost:9090)
- `grafana`: [http://localhost:3000](http://localhost:3000) (default admin/admin)

### Running tests
Install dependencies locally:
```sh
pip install -r requirements.txt
pytest -q
```

Tests include:
- **Smoke tests**: API endpoints
- **Integration tests**: Retry → fail → compensate flow
- **Retry tests**: Jitter and backoff correctness

## Config
Environment variables (see `.env` or `docker-compose.yml`):
- `DATABASE_URL` – DB connection string
- `REDIS_URL` – Redis connection (default `redis://redis:6379/0`)
- `RETRY_MAX_ATTEMPTS`, `RETRY_BASE_DELAY`, `RETRY_BACKOFF`, `RETRY_JITTER_RATIO`

## Notes
- Jobs are executed by workers (RQ), not the API process.
- Failed jobs trigger compensation automatically.
- Metrics can be scraped by Prometheus and visualized in Grafana.

EC2 instance
swagger
http://54.188.148.98:8000/docs
