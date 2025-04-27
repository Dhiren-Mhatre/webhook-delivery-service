from celery import Celery
import os
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND, CELERY_BEAT_SCHEDULE

celery_app = Celery('webhook_delivery_service',
                    broker=CELERY_BROKER_URL,
                    backend=CELERY_RESULT_BACKEND,
                    include=['tasks'])

# Configure Celery
celery_app.conf.update(
    result_expires=3600,  # Results expire after 1 hour
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    beat_schedule=CELERY_BEAT_SCHEDULE,
)

if __name__ == '__main__':
    celery_app.start()
