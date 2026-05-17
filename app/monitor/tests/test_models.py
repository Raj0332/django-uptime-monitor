"""Tests for monitor models."""
import pytest
from django.utils import timezone
from datetime import timedelta

from monitor.models import Check, Incident, Site


class TestSiteCurrentStatus:
    """Tests for Site.current_status property."""

    def test_no_checks_returns_unknown(self, site):
        assert site.current_status == "unknown"

    def test_latest_up_returns_up(self, site, make_check):
        make_check(site, is_up=True)
        assert site.current_status == "up"

    def test_latest_down_returns_down(self, site, make_check):
        make_check(site, is_up=False)
        assert site.current_status == "down"

    def test_uses_latest_check(self, site, make_check):
        # Create an old down check, then a recent up check
        old_check = make_check(site, is_up=False)
        old_check.timestamp = timezone.now() - timedelta(minutes=5)
        old_check.save()
        make_check(site, is_up=True)
        assert site.current_status == "up"


class TestSiteUptimePercent:
    """Tests for Site.uptime_24h_percent and uptime_7d_percent properties."""

    def test_no_checks_returns_zero(self, site):
        assert site.uptime_24h_percent == 0.0
        assert site.uptime_7d_percent == 0.0

    def test_all_up_returns_100(self, site, make_check):
        for _ in range(5):
            make_check(site, is_up=True)
        assert site.uptime_24h_percent == 100.0

    def test_all_down_returns_zero(self, site, make_check):
        for _ in range(5):
            make_check(site, is_up=False)
        assert site.uptime_24h_percent == 0.0

    def test_mixed_uptime(self, site, make_check):
        for _ in range(3):
            make_check(site, is_up=True)
        for _ in range(1):
            make_check(site, is_up=False)
        # 3 up out of 4 = 75%
        assert site.uptime_24h_percent == 75.0

    def test_excludes_old_checks_from_24h(self, site, make_check):
        # Recent up check
        make_check(site, is_up=True)
        # Old down check (outside 24h window)
        old_check = make_check(site, is_up=False)
        old_check.timestamp = timezone.now() - timedelta(hours=25)
        old_check.save()
        assert site.uptime_24h_percent == 100.0


class TestSiteAvgResponseTime:
    """Tests for Site.avg_response_time_24h_ms property."""

    def test_no_checks_returns_none(self, site):
        assert site.avg_response_time_24h_ms is None

    def test_returns_average_of_up_checks(self, site, make_check):
        make_check(site, is_up=True, response_time_ms=100)
        make_check(site, is_up=True, response_time_ms=200)
        assert site.avg_response_time_24h_ms == 150

    def test_excludes_down_checks(self, site, make_check):
        make_check(site, is_up=True, response_time_ms=100)
        make_check(site, is_up=False, response_time_ms=None)
        assert site.avg_response_time_24h_ms == 100


class TestIncidentClose:
    """Tests for Incident.close() method."""

    def test_close_sets_ended_at(self, site, db):
        incident = Incident.objects.create(site=site, started_at=timezone.now() - timedelta(hours=1))
        ended = timezone.now()
        incident.close(ended)
        incident.refresh_from_db()
        assert incident.ended_at == ended

    def test_close_computes_duration_seconds(self, site, db):
        start = timezone.now() - timedelta(seconds=300)
        incident = Incident.objects.create(site=site, started_at=start)
        ended = start + timedelta(seconds=300)
        incident.close(ended)
        incident.refresh_from_db()
        assert incident.duration_seconds == 300

    def test_close_saves_to_db(self, site, db):
        incident = Incident.objects.create(site=site, started_at=timezone.now() - timedelta(minutes=5))
        incident.close(timezone.now())
        from_db = Incident.objects.get(pk=incident.pk)
        assert from_db.ended_at is not None
        assert from_db.duration_seconds is not None
