from django.apps import AppConfig


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"
    verbose_name = "Uptime Monitor"

    def ready(self) -> None:
        # Import metrics so custom Prometheus metrics are registered at startup
        import monitor.metrics  # noqa: F401
