import json
import hashlib
from datetime import datetime

from .db import SessionLocal
from .models import Job, JobStatus, BlockedIP
from .redis import queue
from .retry import retry_with_jitter, load_retry_config


# ---------- Handlers ----------

def execute_hash(payload: dict):
    # Simulate failure if payload requests it (used in integration tests)
    if payload and payload.get("fail"):
        raise RuntimeError("forced failure for testing")

    algo = (payload or {}).get("algo", "sha256")
    data = (payload or {}).get("data", "")
    h = hashlib.new(algo)
    b = data if isinstance(data, bytes) else str(data).encode("utf-8")
    h.update(b)
    return {"algo": algo, "digest": h.hexdigest()}


def compensate_hash(_state: dict):
    return {"compensated": True}


def execute_block_ip(payload: dict):
    ip = (payload or {}).get("ip")
    if not ip:
        raise ValueError("missing ip")
    reason = (payload or {}).get("reason", "policy")

    db = SessionLocal()
    try:
        if not db.get(BlockedIP, ip):
            db.add(BlockedIP(ip=ip, reason=reason))
            db.commit()
        return {"ip": ip, "blocked": True}
    finally:
        db.close()


def compensate_block_ip(state: dict):
    ip = (state or {}).get("ip")
    if not ip:
        return {"compensated": False}
    db = SessionLocal()
    try:
        row = db.get(BlockedIP, ip)
        if row:
            db.delete(row)
            db.commit()
        return {"ip": ip, "unblocked": True}
    finally:
        db.close()


JOB_TYPES = {
    "hash": {"execute": execute_hash, "compensate": compensate_hash},
    "block_ip": {"execute": execute_block_ip, "compensate": compensate_block_ip},
}


# ---------- Enqueue ----------

def enqueue_job(job_id: str, job_type: str, payload: dict):
    queue.enqueue(process_job, job_id, job_type, payload)


# ---------- Retry-wrapped executor ----------

_cfg = load_retry_config()  # returns a dict from .env (with defaults)


def _on_retry(attempt: int, err: Exception, sleep_s: float):
    # keep minimal; no logging needed for tests
    pass


@retry_with_jitter(
    max_attempts=_cfg["max_attempts"],
    base_delay=_cfg["base_delay"],
    backoff=_cfg["backoff"],
    jitter_ratio=_cfg["jitter_ratio"],
    exceptions=(RuntimeError, ValueError, Exception),
    on_retry=_on_retry,
)
def _run(handler, payload):
    return handler(payload)


# ---------- Worker ----------

def process_job(job_id: str, job_type: str, payload: dict):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING.value
        if not job.started_at:
            job.started_at = datetime.utcnow()
        db.commit()

        result = _run(JOB_TYPES[job_type]["execute"], payload)

        job.status = JobStatus.SUCCEEDED.value
        job.attempts += 1
        job.completed_at = datetime.utcnow()
        job.last_error = None
        job.result_json = json.dumps(result)
        db.commit()

    except Exception as e:
        job = db.get(Job, job_id) if 'job' not in locals() else job
        if job:
            job.attempts += 1
            job.last_error = str(e)
            db.commit()

            try:
                comp = JOB_TYPES[job_type]["compensate"]
                comp_state = {"ip": payload.get("ip")} if job_type == "block_ip" else {}
                comp(comp_state)
                job.status = JobStatus.COMPENSATED.value
            except Exception as ce:
                job.status = JobStatus.FAILED.value
                job.compensation_error = str(ce)
            finally:
                job.completed_at = datetime.utcnow()
                db.commit()
    finally:
        db.close()