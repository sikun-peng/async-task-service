import os
import pytest
from starlette.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"
from app import db as app_db
import app.models  # ensure models are registered
import app.main as main


@pytest.fixture(scope="session", autouse=True)
def _setup_db_file():
    # Create schema once per session
    app_db.Base.metadata.create_all(bind=app_db.engine)
    yield
    # Cleanup after all tests
    app_db.Base.metadata.drop_all(bind=app_db.engine)


@pytest.fixture(scope="function")
def client():
    # Fresh schema for each test
    app_db.Base.metadata.drop_all(bind=app_db.engine)
    app_db.Base.metadata.create_all(bind=app_db.engine)
    with TestClient(main.app) as c:
        yield c