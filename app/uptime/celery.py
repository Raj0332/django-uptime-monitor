"""Celery application configuration."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "uptime.settings")

app = Celery("uptime")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Debug task that prints request information."""
    print(f"Request: {self.request!r}")
