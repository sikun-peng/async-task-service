import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

engine = create_engine(
    DATABASE_URL,
    future=True,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

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