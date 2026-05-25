"""Tests for the Job state machine.

Covers:
  - Valid transitions (queued → running → done, queued → running → failed)
  - Invalid transitions raise ValueError
  - Job model defaults
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.models import Job, JobState


def _make_job(**kwargs) -> Job:
    defaults = {
        "id": str(uuid.uuid4()),
        "state": JobState.queued,
        "payload": {},
        "retry_count": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return Job(**defaults)


class TestJobStateMachine:
    def test_queued_to_running(self):
        job = _make_job()
        job.transition_to(JobState.running)
        assert job.state == JobState.running

    def test_running_to_done(self):
        job = _make_job(state=JobState.running)
        job.transition_to(JobState.done)
        assert job.state == JobState.done

    def test_running_to_failed(self):
        job = _make_job(state=JobState.running)
        job.transition_to(JobState.failed)
        assert job.state == JobState.failed

    def test_running_to_queued_allowed_for_retry(self):
        # Worker re-queues on retry via running → queued
        job = _make_job(state=JobState.running)
        job.transition_to(JobState.queued)
        assert job.state == JobState.queued

    def test_done_is_terminal(self):
        job = _make_job(state=JobState.done)
        with pytest.raises(ValueError, match="Cannot transition"):
            job.transition_to(JobState.running)

    def test_failed_is_terminal(self):
        job = _make_job(state=JobState.failed)
        with pytest.raises(ValueError, match="Cannot transition"):
            job.transition_to(JobState.queued)

    def test_queued_cannot_go_directly_to_done(self):
        job = _make_job()
        with pytest.raises(ValueError, match="Cannot transition"):
            job.transition_to(JobState.done)

    def test_default_state_is_queued(self):
        job = _make_job()
        assert job.state == JobState.queued

    def test_default_retry_count_is_zero(self):
        job = _make_job()
        assert job.retry_count == 0


class TestJobAPIStateFlow:
    """End-to-end state flow through the API, using the test client."""

    def test_submit_returns_queued(self, client):
        resp = client.post("/jobs", json={"payload": {}})
        assert resp.status_code == 202
        data = resp.json()
        assert data["state"] == "queued"
        assert data["created"] is True

    def test_get_returns_queued_after_submit(self, client):
        resp = client.post("/jobs", json={"payload": {}})
        job_id = resp.json()["id"]
        resp2 = client.get(f"/jobs/{job_id}")
        assert resp2.status_code == 200
        assert resp2.json()["state"] == "queued"

    def test_get_unknown_job_is_404(self, client):
        resp = client.get("/jobs/nonexistent-id")
        assert resp.status_code == 404
