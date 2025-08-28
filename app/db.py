# app/db.py
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Use env var if set; default to a local sqlite file for dev/tests
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

# Create engine & session factory
engine = create_engine(
    DATABASE_URL,
    future=True,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# Declarative base for all ORM models
Base = declarative_base()

def init_db() -> None:
    """Create database tables once models are registered on Base."""
    # IMPORTANT: ensure models are imported so their tables are registered
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_session():
    """Context manager that yields a session and commits/rolls back cleanly."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()