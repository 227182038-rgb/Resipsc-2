from celery import Celery
from resipsc.config.v3_settings import settings

celery_app = Celery('resipsc_v3', broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND, include=['src.api.tasks'])
celery_app.conf.update(task_serializer='json', accept_content=['json'], result_serializer='json', timezone='UTC', enable_utc=True, task_track_started=True, task_time_limit=3600, worker_prefetch_multiplier=1, worker_max_tasks_per_child=10)

