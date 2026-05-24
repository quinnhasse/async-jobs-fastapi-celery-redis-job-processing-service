"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.stream import router as stream_router
from app.logging_config import RequestLoggingMiddleware, configure_logging
from app.metrics import router as metrics_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    configure_logging()
    log.info("async-jobs starting up")
    yield
    log.info("async-jobs shutting down")


app = FastAPI(
    title="async-jobs",
    description="FastAPI + Celery + Redis job-processing service. POST a job, poll for status.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)

app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(stream_router)
app.include_router(metrics_router)
