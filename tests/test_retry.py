"""Tests for worker retry behaviour and dead-letter state.

These tests exercise the task logic directly against a SQLite session,
bypassing Celery's broker entirely.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, JobState
from app.worker.tasks import (
    _execute_payload,
    _mark_failed,
    _refresh_retry_count,
    run_job,
)


@pytest.fixture(scope="module")
def task_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def task_db(task_engine):
    conn = task_engine.connect()
    txn = conn.begin()
    Session = sessionmaker(bind=conn)
    session = Session()
    yield session
    session.close()
    txn.rollback()
    conn.close()


def _insert_job(session, state=JobState.queued, payload=None) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        state=state,
        retry_count=0,
        payload=payload or {},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(job)
    session.commit()
    return job


class TestExecutePayload:
    def test_success_with_empty_payload(self):
        _execute_payload({})  # should not raise

    def test_fail_flag_raises(self):
        with pytest.raises(RuntimeError, match="simulated task failure"):
            _execute_payload({"fail": True})

    def test_sleep_capped_at_30(self, mocker):
        mock_sleep = mocker.patch("app.worker.tasks.time.sleep")
        _execute_payload({"sleep": 999})
        mock_sleep.assert_called_once_with(30.0)


class TestMarkFailed:
    def test_sets_failed_state(self, task_db):
        job = _insert_job(task_db, state=JobState.running)
        _mark_failed(task_db, job.id, "boom")
        task_db.expire(job)
        fresh = task_db.get(Job, job.id)
        assert fresh.state == JobState.failed
        assert fresh.error == "boom"

    def test_noop_for_missing_job(self, task_db):
        _mark_failed(task_db, "nonexistent-id", "irrelevant")  # should not raise


class TestRefreshRetryCount:
    def test_updates_retry_count(self, task_db):
        job = _insert_job(task_db)
        _refresh_retry_count(task_db, job.id, 2)
        task_db.expire(job)
        fresh = task_db.get(Job, job.id)
        assert fresh.retry_count == 2


class TestRunJob:
    def test_successful_job_transitions_to_done(self, task_db):
        job = _insert_job(task_db, payload={"sleep": 0})
        result = run_job(task_db, job.id, retries=0)
        task_db.expire(job)
        fresh = task_db.get(Job, job.id)
        assert fresh.state == JobState.done
        assert result["state"] == "done"

    def test_successful_job_stores_result(self, task_db):
        job = _insert_job(task_db, payload={"x": 42})
        run_job(task_db, job.id, retries=0)
        task_db.expire(job)
        fresh = task_db.get(Job, job.id)
        assert fresh.result == {"processed": True, "payload": {"x": 42}}

    def test_failed_payload_raises_and_updates_retry_count(self, task_db):
        job = _insert_job(task_db, payload={"fail": True})
        with pytest.raises(RuntimeError, match="simulated task failure"):
            run_job(task_db, job.id, retries=1)
        task_db.expire(job)
        fresh = task_db.get(Job, job.id)
        assert fresh.state == JobState.running
        assert fresh.retry_count == 1

    def test_missing_job_returns_not_found(self, task_db):
        result = run_job(task_db, "does-not-exist", retries=0)
        assert result["status"] == "not_found"

    def test_already_done_job_is_skipped(self, task_db):
        job = _insert_job(task_db, state=JobState.done)
        result = run_job(task_db, job.id, retries=0)
        assert result["status"] == "skipped"
        # State must not change
        task_db.expire(job)
        fresh = task_db.get(Job, job.id)
        assert fresh.state == JobState.done
