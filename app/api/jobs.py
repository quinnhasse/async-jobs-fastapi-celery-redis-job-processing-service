"""Job submission and status endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.metrics import jobs_queued
from app.models import Job, JobState
from app.schemas import JobCreate, JobResponse, JobSubmitResponse
from app.worker.tasks import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(
    body: JobCreate,
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JobSubmitResponse:
    """Enqueue a new job.

    If an ``Idempotency-Key`` header is supplied and a job with that key already
    exists, the existing job is returned unchanged (``created=False``).
    """
    # Idempotency check
    if idempotency_key:
        existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
        if existing:
            return JobSubmitResponse(id=existing.id, state=existing.state, created=False)

    job = Job(
        id=str(uuid.uuid4()),
        idempotency_key=idempotency_key,
        state=JobState.queued,
        payload=body.payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    process_job.delay(job.id)
    jobs_queued.inc()

    return JobSubmitResponse(id=job.id, state=job.state, created=True)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Annotated[Session, Depends(get_db)]) -> Job:
    """Return the current state and result of a job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job
