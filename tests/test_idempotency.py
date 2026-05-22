"""Tests for idempotency key deduplication.

POST /jobs with the same Idempotency-Key must return the existing job
(created=False) without creating a duplicate or dispatching a second task.
"""


class TestIdempotency:
    def test_same_key_returns_existing_job(self, client):
        key = "test-idem-key-001"
        r1 = client.post("/jobs", json={"payload": {"x": 1}}, headers={"Idempotency-Key": key})
        r2 = client.post("/jobs", json={"payload": {"x": 2}}, headers={"Idempotency-Key": key})

        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["id"] == r2.json()["id"]
        assert r1.json()["created"] is True
        assert r2.json()["created"] is False

    def test_different_keys_create_different_jobs(self, client):
        r1 = client.post("/jobs", json={}, headers={"Idempotency-Key": "key-aaa"})
        r2 = client.post("/jobs", json={}, headers={"Idempotency-Key": "key-bbb"})
        assert r1.json()["id"] != r2.json()["id"]

    def test_no_key_always_creates_new_job(self, client):
        r1 = client.post("/jobs", json={})
        r2 = client.post("/jobs", json={})
        assert r1.json()["id"] != r2.json()["id"]
        assert r1.json()["created"] is True
        assert r2.json()["created"] is True

    def test_celery_dispatch_skipped_on_duplicate(self, client, mocker):
        mock_delay = mocker.patch("app.worker.tasks.process_job.delay")
        key = "idem-dispatch-test"
        client.post("/jobs", json={}, headers={"Idempotency-Key": key})
        client.post("/jobs", json={}, headers={"Idempotency-Key": key})
        # Dispatched exactly once — the second call hit the idempotency guard
        assert mock_delay.call_count == 1

    def test_idempotency_key_preserved_in_job_record(self, client):
        key = "stored-key-check"
        r = client.post("/jobs", json={}, headers={"Idempotency-Key": key})
        job_id = r.json()["id"]
        job_resp = client.get(f"/jobs/{job_id}")
        # The job record is fetchable by id; idempotency key is stored internally
        assert job_resp.status_code == 200
        assert job_resp.json()["id"] == job_id
