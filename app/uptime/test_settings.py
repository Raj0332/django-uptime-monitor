"""Test-specific Django settings — extends base settings with test overrides."""
from uptime.settings import *  # noqa: F401, F403

# Run Celery tasks synchronously in tests so .delay() calls work without a broker
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Use in-memory cache so tests don't require a running Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Silence logging noise during test runs
LOGGING["root"]["level"] = "WARNING"  # type: ignore[index]
