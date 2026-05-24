"""Celery tasks for async job processing.

Each task follows this lifecycle:
  1. Mark the job as running at task start.
  2. Execute the payload operation.
  3. Mark done on success, or increment retry_count and re-raise.
  4. On final retry exhaustion, mark the job as failed and store the error.
"""

import logging
import time

from celery import Task
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy.orm import Session

from app.config import settings
from app.metrics import jobs_completed, jobs_failed, jobs_retried, task_duration
from app.models import Job, JobState
from app.worker.celery_app import celery_app

log = logging.getLogger(__name__)


def _get_db_session() -> Session:
    """Return a new database session for task use (not the FastAPI request scope)."""
    from app.database import SessionLocal

    return SessionLocal()


class JobTask(Task):
    """Base task that manages DB session lifecycle."""

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:  # noqa: ANN001
        log.error("task %s failed permanently: %s", task_id, exc)


def run_job(db: Session, job_id: str, retries: int = 0) -> dict:
    """Core job execution logic — shared by the Celery task and tests.

    Transitions job from queued/running → running, executes the payload,
    then transitions to done on success. Raises on failure so the caller
    (the Celery task) can retry or mark failed.
    """
    job = db.get(Job, job_id)
    if job is None:
        log.error("job %s not found — skipping", job_id)
        return {"status": "not_found"}

    # Transition to running only from queued (or re-queued on retry)
    if job.state in (JobState.queued, JobState.running):
        try:
            job.transition_to(JobState.running)
        except ValueError:
            pass  # already running from a previous attempt in this task
        job.retry_count = retries
        db.commit()
    else:
        log.warning("job %s in unexpected state %r — skipping", job_id, job.state)
        return {"status": "skipped", "state": job.state}

    # --- Payload operation ---
    payload = job.payload or {}
    with task_duration.time():
        _execute_payload(payload)
    # -------------------------

    job.transition_to(JobState.done)
    job.result = {"processed": True, "payload": payload}
    db.commit()
    jobs_completed.inc()
    log.info("job %s completed", job_id)
    return {"job_id": job_id, "state": "done"}


@celery_app.task(
    bind=True,
    base=JobTask,
    name="app.worker.tasks.process_job",
    max_retries=settings.task_max_retries,
    default_retry_delay=settings.task_retry_backoff,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_job(self: Task, job_id: str) -> dict:
    """Celery task wrapper for run_job."""
    db: Session = _get_db_session()
    try:
        return run_job(db, job_id, retries=self.request.retries)
    except MaxRetriesExceededError:
        _mark_failed(db, job_id, "max retries exceeded")
        return {"job_id": job_id, "state": "failed"}
    except Exception as exc:
        _refresh_retry_count(db, job_id, self.request.retries)
        jobs_retried.inc()
        log.warning("job %s attempt %d failed: %s", job_id, self.request.retries, exc)
        raise
    finally:
        db.close()


def _execute_payload(payload: dict) -> None:
    """Simulate a unit of work.

    If payload contains ``{"fail": true}`` this raises to trigger retry logic.
    If payload contains ``{"sleep": N}`` this sleeps N seconds (max 30).
    """
    if payload.get("fail"):
        raise RuntimeError("simulated task failure (payload.fail=true)")
    sleep_s = min(float(payload.get("sleep", 0)), 30.0)
    if sleep_s > 0:
        time.sleep(sleep_s)


def _mark_failed(db: Session, job_id: str, reason: str) -> None:
    """Unconditionally set a job to failed state and store the error."""
    job = db.get(Job, job_id)
    if job is None:
        return
    try:
        job.state = JobState.failed
        job.error = reason
        db.commit()
    except Exception:
        db.rollback()
    jobs_failed.inc()
    log.error("job %s marked failed: %s", job_id, reason)


def _refresh_retry_count(db: Session, job_id: str, attempt: int) -> None:
    """Update the retry_count on a job record."""
    job = db.get(Job, job_id)
    if job is None:
        return
    job.retry_count = attempt
    try:
        db.commit()
    except Exception:
        db.rollback()
