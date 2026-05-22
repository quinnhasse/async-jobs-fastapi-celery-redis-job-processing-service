"""Test configuration and shared fixtures.

All tests run against an in-memory SQLite database. Celery task dispatch is
patched out at the API layer so tests don't require a running broker.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create a single in-memory SQLite engine for the test session."""
    eng = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    """Yield a transactional session that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session, mocker):
    """FastAPI test client with DB wired to the test session and Celery patched."""
    # Patch Celery task dispatch so tests don't need a broker.
    # process_job is imported at the top of app.api.jobs, so patch it there.
    mocker.patch("app.worker.tasks.process_job.delay", return_value=None)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
