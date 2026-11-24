"""IRYX Celery Application and Worker Configuration."""

import logging

from celery import Celery
from kombu.utils.url import sanitize_url

from iryx.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "iryx",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

celery_app.autodiscover_tasks(["iryx.evidence"])


def mask_broker_url(url: str) -> str:
    """Mask sensitive credentials in a broker URL for secure logging."""
    try:
        return sanitize_url(url)
    except Exception:
        return "***REDACTED***"


def check_broker_connection(timeout: float = 2.0) -> bool:
    """Verify network connectivity to the Celery broker without crashing.

    Logs a structured JSON error if the broker is unreachable.
    Returns True if connection succeeds, False otherwise.
    """
    try:
        with celery_app.connection_for_read() as conn:
            conn.ensure_connection(max_retries=0, timeout=timeout)
        return True
    except Exception as exc:
        logger.error(
            "Échec de connexion au courtier Celery/Redis",
            extra={
                "context": {
                    "broker_url": mask_broker_url(settings.celery_broker_url),
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "timeout": timeout,
                }
            },
            exc_info=True,
        )
        return False
