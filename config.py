import os
from datetime import timedelta

SECRET_KEY = os.environ.get("SESSION_SECRET", "webhook-delivery-service-secret-key")
DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "t")

SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@db:5432/webhookdb"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
REDIS_CACHE_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

MAX_RETRY_ATTEMPTS = 5
RETRY_DELAYS = [10, 30, 60, 300, 900]  # in seconds (10s, 30s, 1m, 5m, 15m)
DELIVERY_TIMEOUT = 10  # seconds

# Log retention period (in hours)
LOG_RETENTION_PERIOD = 72  # 72 hours = 3 days

# Celery beat schedule for log cleanup
CELERY_BEAT_SCHEDULE = {
    'cleanup-delivery-logs': {
        'task': 'tasks.cleanup_old_delivery_logs',
        'schedule': timedelta(hours=1),  # Run every hour
    },
}

# Cache configuration
CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes