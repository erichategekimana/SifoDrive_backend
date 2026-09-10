"""
Sifo Drive — Celery Application Configuration
===============================================
Handles async tasks: SMS dispatch, MoMo webhook processing,
proctoring snapshot purge, report generation.
"""

import os

from celery import Celery
from celery.utils.log import get_task_logger

# Set default Django settings for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("sifo_drive")

# Read Celery config from Django settings (prefix: CELERY_)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

logger = get_task_logger(__name__)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Health-check task for verifying Celery worker connectivity."""
    logger.info("Celery worker healthy. Request: %r", self.request)
