import uuid
import json
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, String, Integer, DateTime, Text
from .db import Base


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type = Column(String(64), nullable=False)
    payload = Column(Text, nullable=True)            # store JSON as text for simplicity
    idempotency_key = Column(String(128), nullable=True, index=True)
    status = Column(String(32), nullable=False, default=JobStatus.QUEUED.value)
    attempts = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_error = Column(Text, nullable=True)
    compensation_error = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.job_type,
            "status": self.status,
            "attempts": self.attempts,
            "lastError": self.last_error,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }

    def get_payload(self) -> Optional[dict]:
        return json.loads(self.payload) if self.payload else None