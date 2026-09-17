"""Celery application.

Workers handle the receipt outbox, bulk activation orchestration and report
processing. Nothing a worker does may change a verification outcome: by the time
a job runs, the outcome is already committed.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("anticounterfeitmed")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
