from celery import Celery

from app.config import settings

celery_app = Celery(
    "async-jobs",
    broker=settings.redis_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Routing — dead-letter queue for exhausted jobs
    task_routes={
        "app.worker.tasks.process_job": {"queue": "default"},
    },
    task_queues_max_priority=10,
    # Retry behaviour
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Result expiry
    result_expires=86400,  # 24 h
    # Worker concurrency
    worker_prefetch_multiplier=1,
)
