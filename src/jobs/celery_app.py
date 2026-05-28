from celery import Celery
from src.config import settings

celery_app = Celery(
    "ridedelivery",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.jobs.ride_tasks",
        "src.jobs.notification_tasks",
        "src.jobs.payment_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Nairobi",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,         # Re-queue if worker dies mid-task
    worker_prefetch_multiplier=1,  # Fair dispatch under high load
    task_routes={
        "src.jobs.ride_tasks.*": {"queue": "rides"},
        "src.jobs.notification_tasks.*": {"queue": "notifications"},
        "src.jobs.payment_tasks.*": {"queue": "payments"},
    },
)
