from datetime import datetime, timedelta
from typing import Optional

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Site(models.Model):
    """A monitored website or endpoint.

    Stores configuration for how and how often to check a URL, and exposes
    computed properties for current status, uptime percentages, and average
    response time derived from the related Check records.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sites")
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    check_interval_seconds = models.IntegerField(
        default=60,
        validators=[MinValueValidator(30)],
        help_text="How often to check this site, in seconds (minimum 30).",
    )
    timeout_seconds = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="HTTP request timeout in seconds (1–60).",
    )
    expected_status_code = models.IntegerField(
        default=200,
        help_text="The HTTP status code considered as 'up' (usually 200).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.url})"

    @property
    def current_status(self) -> str:
        """Return the site's current status based on the most recent Check.

        Returns:
            'up'      – most recent check was successful
            'down'    – most recent check failed
            'unknown' – no checks have been recorded yet
        """
        latest = self.checks.first()  # ordered by -timestamp via Check.Meta
        if latest is None:
            return "unknown"
        return "up" if latest.is_up else "down"

    @property
    def uptime_24h_percent(self) -> float:
        """Return the percentage of checks that were 'up' in the last 24 hours.

        Returns 0.0 if no checks exist in the window.
        """
        since = timezone.now() - timedelta(hours=24)
        qs = self.checks.filter(timestamp__gte=since)
        total = qs.count()
        if total == 0:
            return 0.0
        up_count = qs.filter(is_up=True).count()
        return round(up_count / total * 100, 2)

    @property
    def uptime_7d_percent(self) -> float:
        """Return the percentage of checks that were 'up' in the last 7 days.

        Returns 0.0 if no checks exist in the window.
        """
        since = timezone.now() - timedelta(days=7)
        qs = self.checks.filter(timestamp__gte=since)
        total = qs.count()
        if total == 0:
            return 0.0
        up_count = qs.filter(is_up=True).count()
        return round(up_count / total * 100, 2)

    @property
    def avg_response_time_24h_ms(self) -> Optional[int]:
        """Return the average response time (ms) for successful checks in the last 24h.

        Returns None if there are no successful checks in the window.
        """
        since = timezone.now() - timedelta(hours=24)
        result = (
            self.checks.filter(timestamp__gte=since, is_up=True)
            .aggregate(avg=models.Avg("response_time_ms"))
        )
        avg = result["avg"]
        if avg is None:
            return None
        return int(avg)


class Check(models.Model):
    """A single HTTP check result for a Site.

    Each time the monitoring worker probes a Site it creates one Check record
    capturing the outcome, timing, and any error details.
    """

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="checks")
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    is_up = models.BooleanField()
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["site", "-timestamp"]),
        ]

    def __str__(self) -> str:
        status = "UP" if self.is_up else "DOWN"
        return f"[{status}] {self.site.name} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"


class Incident(models.Model):
    """A period during which a Site was detected as down.

    An Incident is opened when a site transitions from 'up' to 'down' and
    closed (via :meth:`close`) when it recovers.
    """

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="incidents")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        if self.ended_at:
            return f"Incident for {self.site.name} ({self.started_at:%Y-%m-%d %H:%M} – {self.ended_at:%H:%M})"
        return f"OPEN Incident for {self.site.name} since {self.started_at:%Y-%m-%d %H:%M}"

    def close(self, ended_at: datetime) -> None:
        """Close the incident, recording the end time and computing duration.

        Args:
            ended_at: The datetime at which the site recovered.
        """
        self.ended_at = ended_at
        self.duration_seconds = int((ended_at - self.started_at).total_seconds())
        self.save()


class AlertChannel(models.Model):
    """A notification channel through which alerts are delivered to a user.

    Supported channel types are email and webhook. The ``config`` JSONField
    holds channel-specific settings (e.g. ``{"email": "user@example.com"}``
    or ``{"url": "https://hooks.example.com/..."}``) .
    """

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("webhook", "Webhook"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="alert_channels")
    channel_type = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    config = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["user", "channel_type"]

    def __str__(self) -> str:
        return f"{self.get_channel_type_display()} channel for {self.user.username}"
