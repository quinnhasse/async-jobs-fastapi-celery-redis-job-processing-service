"""Prometheus metrics for the worker and API.

Metrics exposed:
  - async_jobs_queued_total: counter of jobs submitted
  - async_jobs_completed_total: counter of jobs that reached done state
  - async_jobs_failed_total: counter of jobs that reached failed state
  - async_jobs_task_duration_seconds: histogram of task execution time
  - async_jobs_retry_total: counter of task retry attempts

Import ``record_*`` helpers from worker/task code. The ``/metrics`` endpoint
is registered in app/main.py.
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

router = APIRouter(tags=["metrics"])

# --- Counters ---
jobs_queued = Counter(
    "async_jobs_queued_total",
    "Total number of jobs submitted via POST /jobs",
)

jobs_completed = Counter(
    "async_jobs_completed_total",
    "Total number of jobs that transitioned to done state",
)

jobs_failed = Counter(
    "async_jobs_failed_total",
    "Total number of jobs that transitioned to failed state",
)

jobs_retried = Counter(
    "async_jobs_retry_total",
    "Total number of Celery task retry attempts",
)

# --- Histograms ---
task_duration = Histogram(
    "async_jobs_task_duration_seconds",
    "Time spent executing a job task (excluding queue wait)",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


@router.get("/metrics", include_in_schema=False)
def metrics_endpoint() -> Response:
    """Expose Prometheus metrics in text format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
