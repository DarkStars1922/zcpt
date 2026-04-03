from celery import Celery

from app.core.config import settings

broker_url = settings.redis_url if settings.redis_enabled else "memory://"
result_backend = settings.redis_url if settings.redis_enabled else "cache+memory://"

celery_app = Celery(
    "zcpt",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.jobs"],
)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_eager_propagates,
    result_expires=settings.celery_result_expires_seconds,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
