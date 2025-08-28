import json
import hashlib
import socket
import logging
from datetime import datetime

from .db import SessionLocal
from .models import Job, JobStatus
from .redis import queue
from .retry import retry_with_jitter, load_retry_config
from .metrics import JOBS_PROCESSED

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

hostname = socket.gethostname()  # identify which worker replica


# ---------------- Hash jobs ----------------
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


# ---------------- Block IP jobs ----------------
def execute_block_ip(payload: dict):
    ip = (payload or {}).get("ip")
    if not ip:
        raise ValueError("missing ip")
    reason = (payload or {}).get("reason", "policy")

    # Instead of persisting to a BlockedIP table, just return the result
    return {"ip": ip, "blocked": True, "reason": reason}


def compensate_block_ip(state: dict):
    ip = (state or {}).get("ip")
    if not ip:
        return {"compensated": False}
    # No DB persistence — just simulate unblock
    return {"ip": ip, "unblocked": True}


# ---------------- Registry ----------------
JOB_TYPES = {
    "hash": {"execute": execute_hash, "compensate": compensate_hash},
    "block_ip": {"execute": execute_block_ip, "compensate": compensate_block_ip},
}


def enqueue_job(job_id: str, job_type: str, payload: dict):
    queue.enqueue(process_job, job_id, job_type, payload)


# ---------------- Retry + runner ----------------
_cfg = load_retry_config()  # returns a dict from .env (with defaults)


def _on_retry(attempt: int, err: Exception, sleep_s: float):
    logger.warning(f"[{hostname}] Retry {attempt} after error: {err}, sleeping {sleep_s:.2f}s")


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


# ---------------- Worker entrypoint ----------------
def process_job(job_id: str, job_type: str, payload: dict):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            logger.warning(f"[{hostname}] Job {job_id} not found")
            return

        job.status = JobStatus.RUNNING.value
        if not job.started_at:
            job.started_at = datetime.utcnow()
        db.commit()

        logger.info(f"[{hostname}] Starting job {job_id} type={job_type}")

        # run actual executor
        result = _run(JOB_TYPES[job_type]["execute"], payload)

        # mark success
        job.status = JobStatus.SUCCEEDED.value
        job.attempts += 1
        job.completed_at = datetime.utcnow()
        job.last_error = None
        job.result_json = json.dumps({**result, "worker": hostname})
        db.commit()

        JOBS_PROCESSED.labels(status="SUCCEEDED").inc()
        logger.info(f"[{hostname}] Job {job_id} SUCCEEDED")

    except Exception as e:
        job = db.get(Job, job_id) if "job" not in locals() else job
        if job:
            job.attempts += 1
            job.last_error = str(e)
            db.commit()

            logger.error(f"[{hostname}] Job {job_id} FAILED: {e}")

            try:
                comp = JOB_TYPES[job_type]["compensate"]
                comp_state = {"ip": payload.get("ip")} if job_type == "block_ip" else {}
                comp_result = comp(comp_state)
                job.status = JobStatus.COMPENSATED.value
                job.result_json = json.dumps({**comp_result, "worker": hostname})

                JOBS_PROCESSED.labels(status="COMPENSATED").inc()
                logger.info(f"[{hostname}] Job {job_id} COMPENSATED")

            except Exception as ce:
                job.status = JobStatus.FAILED.value
                job.compensation_error = str(ce)

                JOBS_PROCESSED.labels(status="FAILED").inc()
                logger.error(f"[{hostname}] Job {job_id} COMPENSATION FAILED: {ce}")

            finally:
                job.completed_at = datetime.utcnow()
                db.commit()
    finally:
        db.close()