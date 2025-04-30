"""
Celery application for Document Scanner.

This module sets up the Celery application for asynchronous processing of document tasks.
"""

import os
from celery import Celery
from config.settings import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_TASK_SERIALIZER,
    CELERY_RESULT_SERIALIZER,
    CELERY_ACCEPT_CONTENT,
    CELERY_TIMEZONE,
    CELERY_TASK_DEFAULT_QUEUE,
    CELERY_ENABLED
)
from utils.logging_utils import setup_logger

# Set up the logger
logger = setup_logger(__name__)

# Create the Celery application
app = Celery('document_scanner')

# Configure the Celery application
app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    task_serializer=CELERY_TASK_SERIALIZER,
    result_serializer=CELERY_RESULT_SERIALIZER,
    accept_content=CELERY_ACCEPT_CONTENT,
    timezone=CELERY_TIMEZONE,
    task_default_queue=CELERY_TASK_DEFAULT_QUEUE,
    task_track_started=True,
    worker_hijack_root_logger=False,  # Use our own logger
)

# Include tasks module
app.autodiscover_tasks(['app.tasks'])

# Check if Celery is enabled
if not CELERY_ENABLED:
    logger.warning("Celery is disabled in settings. Task execution will fall back to synchronous mode.")

# Define a function to check if Celery workers are available
def is_celery_available():
    """Check if Celery workers are available."""
    if not CELERY_ENABLED:
        return False
        
    try:
        # Check if inspection results in active workers
        inspection = app.control.inspect()
        active_workers = inspection.active()
        if active_workers:
            logger.info(f"Celery workers available: {list(active_workers.keys())}")
            return True
        else:
            logger.warning("No active Celery workers found")
            return False
    except Exception as e:
        logger.error(f"Failed to check for Celery workers: {str(e)}")
        return False