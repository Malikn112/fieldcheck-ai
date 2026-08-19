"""
Optional Celery application (Redis-backed) for offloading vision-analysis
processing to a separate worker process at scale.

By default (`USE_CELERY=false`) the API uses FastAPI `BackgroundTasks`
instead, which is simpler and requires no Redis for local dev/demo. Flip
`USE_CELERY=true` (and run `celery -A app.services.celery_app worker`) to
switch to the distributed queue path — the task body is identical either
way; see `app.services.inspection_pipeline.process_inspection`.
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "fieldcheck",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=settings.vision_timeout_seconds * (settings.vision_max_retries + 1) + 30,
    worker_hijack_root_logger=False,
)


@celery_app.task(name="fieldcheck.process_inspection", bind=True, max_retries=0)
def process_inspection_task(self, inspection_id: str) -> str:
    """Celery entrypoint — runs the async pipeline synchronously inside the
    worker's own event loop."""
    import asyncio

    from app.services.inspection_pipeline import process_inspection

    asyncio.run(process_inspection(inspection_id))
    return inspection_id
