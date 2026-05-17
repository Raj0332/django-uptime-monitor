"""Tests for Celery tasks."""
import pytest
import responses as responses_lib
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from monitor.models import Check, Incident, Site
from monitor.tasks import check_site, detect_incident, dispatch_checks


class TestCheckSiteTask:
    """Tests for check_site Celery task."""

    @responses_lib.activate
    def test_happy_path_creates_check_up(self, site, db):
        responses_lib.add(
            responses_lib.GET,
            site.url,
            json={"ok": True},
            status=200,
        )
        result = check_site(site.id)
        assert result["is_up"] is True
        check = Check.objects.filter(site=site).first()
        assert check is not None
        assert check.is_up is True
        assert check.status_code == 200
        assert check.response_time_ms is not None

    @responses_lib.activate
    def test_happy_path_updates_last_checked_at(self, site, db):
        responses_lib.add(responses_lib.GET, site.url, status=200)
        check_site(site.id)
        site.refresh_from_db()
        assert site.last_checked_at is not None

    @responses_lib.activate
    def test_wrong_status_code_is_down(self, site, db):
        responses_lib.add(responses_lib.GET, site.url, status=404)
        result = check_site(site.id)
        assert result["is_up"] is False
        check = Check.objects.filter(site=site).first()
        assert check.is_up is False

    @responses_lib.activate
    def test_connection_error_creates_down_check(self, site, db):
        import requests as req_lib
        responses_lib.add(
            responses_lib.GET,
            site.url,
            body=req_lib.ConnectionError("Connection refused"),
        )
        result = check_site(site.id)
        assert result["is_up"] is False
        check = Check.objects.filter(site=site).first()
        assert check is not None
        assert check.is_up is False
        assert check.error_message != ""

    def test_inactive_site_is_skipped(self, site, db):
        site.is_active = False
        site.save()
        result = check_site(site.id)
        assert result["skipped"] is True
        assert Check.objects.filter(site=site).count() == 0

    def test_nonexistent_site_returns_skipped(self, db):
        result = check_site(99999)
        assert result["skipped"] is True

    @responses_lib.activate
    def test_timeout_creates_down_check(self, site, db):
        import requests as req_lib
        responses_lib.add(
            responses_lib.GET,
            site.url,
            body=req_lib.Timeout("timed out"),
        )
        result = check_site(site.id)
        assert result["is_up"] is False
        check = Check.objects.filter(site=site).first()
        assert check.is_up is False
        assert "Timeout" in check.error_message or "timeout" in check.error_message.lower()


class TestDispatchChecksTask:
    """Tests for dispatch_checks Celery task."""

    def test_enqueues_site_with_null_last_checked(self, site, db):
        with patch("monitor.tasks.check_site") as mock_task:
            mock_task.delay = lambda site_id: None
            count = dispatch_checks()
        assert count == 1

    def test_enqueues_site_past_interval(self, site, db):
        site.last_checked_at = timezone.now() - timedelta(seconds=site.check_interval_seconds + 10)
        site.save()
        with patch("monitor.tasks.check_site") as mock_task:
            mock_task.delay = lambda site_id: None
            count = dispatch_checks()
        assert count == 1

    def test_skips_site_recently_checked(self, site, db):
        site.last_checked_at = timezone.now()
        site.save()
        with patch("monitor.tasks.check_site") as mock_task:
            mock_task.delay = lambda site_id: None
            count = dispatch_checks()
        assert count == 0

    def test_skips_inactive_site(self, site, db):
        site.is_active = False
        site.save()
        with patch("monitor.tasks.check_site") as mock_task:
            mock_task.delay = lambda site_id: None
            count = dispatch_checks()
        assert count == 0


class TestDetectIncidentTask:
    """Tests for detect_incident Celery task."""

    def test_opens_incident_after_3_failures(self, site, make_check, db):
        for _ in range(3):
            make_check(site, is_up=False)
        result = detect_incident(site.id)
        assert result["action"] == "opened"
        assert Incident.objects.filter(site=site, ended_at__isnull=True).exists()

    def test_does_not_open_with_only_2_failures(self, site, make_check, db):
        for _ in range(2):
            make_check(site, is_up=False)
        result = detect_incident(site.id)
        assert result["action"] == "none"
        assert not Incident.objects.filter(site=site).exists()

    def test_closes_incident_on_recovery(self, site, make_check, db):
        incident = Incident.objects.create(site=site, started_at=timezone.now() - timedelta(minutes=10))
        make_check(site, is_up=True)
        result = detect_incident(site.id)
        assert result["action"] == "closed"
        incident.refresh_from_db()
        assert incident.ended_at is not None

    def test_does_not_open_duplicate_incident(self, site, make_check, db):
        Incident.objects.create(site=site, started_at=timezone.now() - timedelta(minutes=5))
        for _ in range(3):
            make_check(site, is_up=False)
        detect_incident(site.id)
        assert Incident.objects.filter(site=site, ended_at__isnull=True).count() == 1

    def test_no_checks_returns_none_action(self, site, db):
        result = detect_incident(site.id)
        assert result["action"] == "none"
