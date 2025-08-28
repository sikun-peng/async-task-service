import uuid
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from prometheus_fastapi_instrumentator import Instrumentator
import rq

from .db import SessionLocal, Base, engine
from .models import Job, JobStatus
from . import tasks
from .redis import queue

app = FastAPI(title="Async Task Service", version="1.0")
Instrumentator().instrument(app).expose(app)


# --- Startup: init DB + metrics ---
@app.on_event("startup")
def on_startup():
    print("Initializing DB...")
    Base.metadata.create_all(bind=engine)


# --- Dependency: DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Healthcheck ---
@app.get("/health")
def health():
    return {"status": "ok"}


# --- POST /v1/jobs ---
@app.post("/v1/jobs")
def create_job(job: dict, db: Session = Depends(get_db)):
    job_type = job.get("type")
    payload = job.get("payload")
    idempotency_key = job.get("idempotencyKey")

    if not job_type:
        raise HTTPException(status_code=400, detail="Missing job type")

    # idempotency check
    if idempotency_key:
        existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
        if existing:
            return {"jobId": existing.id}

    job_id = str(uuid.uuid4())
    db_job = Job(
        id=job_id,
        job_type=job_type,
        payload=json.dumps(payload) if payload is not None else None,
        idempotency_key=idempotency_key,
        status=JobStatus.QUEUED.value,
        created_at=datetime.utcnow(),
    )
    db.add(db_job)
    db.commit()

    # enqueue into worker
    queue.enqueue(tasks.process_job, job_id, job_type, payload)
    return {"jobId": job_id}


# --- GET /v1/jobs/{jobId} ---
@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


# --- Optional: GET /v1/jobs (list recent first) ---
@app.get("/v1/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return [j.to_dict() for j in jobs]