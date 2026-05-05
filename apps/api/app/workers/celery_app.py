from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rumi",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_routes={
        "app.workers.tasks.generate.*": {"queue": "generation_queue"},
        "app.workers.tasks.cv_analyze.*": {"queue": "cv_queue"},
        "app.workers.tasks.match.*": {"queue": "matching_queue"},
    },
)

# Автоматически находим задачи
celery_app.autodiscover_tasks(["app.workers.tasks"])
