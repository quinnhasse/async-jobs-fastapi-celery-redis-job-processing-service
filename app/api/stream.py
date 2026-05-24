"""Server-Sent Events endpoint for live job status.

GET /jobs/{id}/stream emits an event each time the job state changes,
then closes the connection when the job reaches a terminal state
(done or failed).

The client can poll cheaply by opening one long-lived SSE connection
instead of repeating GET /jobs/{id}.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models import Job, JobState

router = APIRouter(tags=["stream"])

TERMINAL_STATES = {JobState.done, JobState.failed}
POLL_INTERVAL_S = 1.0


@router.get("/jobs/{job_id}/stream")
async def stream_job_status(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> EventSourceResponse:
    """Stream state-change events for a job until it reaches a terminal state.

    Each event has the format::

        data: {"id": "...", "state": "running"}

    The stream closes automatically once state is ``done`` or ``failed``.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    async def event_generator():
        last_state = None
        while True:
            db.expire(job)
            current_job = db.get(Job, job_id)
            if current_job is None:
                break
            if current_job.state != last_state:
                last_state = current_job.state
                yield {
                    "event": "state_change",
                    "data": f'{{"id": "{job_id}", "state": "{current_job.state.value}"}}',
                }
            if current_job.state in TERMINAL_STATES:
                break
            await asyncio.sleep(POLL_INTERVAL_S)

    return EventSourceResponse(event_generator())
