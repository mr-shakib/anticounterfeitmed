"""Project package.

Importing the Celery app here means ``shared_task`` resolves against it whenever
Django starts.
"""

from config.celery import app as celery_app

__all__ = ["celery_app"]
