from django.core.management.base import BaseCommand

from monitor.metrics import current_open_incidents, sites_active_total
from monitor.models import Incident, Site


class Command(BaseCommand):
    """Management command to update Prometheus gauge metrics."""

    help = "Update Prometheus gauge metrics for current state"

    def handle(self, *args, **options) -> None:
        """Update current_open_incidents and sites_active_total gauges."""
        open_incidents = Incident.objects.filter(ended_at__isnull=True).count()
        active_sites = Site.objects.filter(is_active=True).count()
        current_open_incidents.set(open_incidents)
        sites_active_total.set(active_sites)
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated gauges: open_incidents={open_incidents}, active_sites={active_sites}"
            )
        )
