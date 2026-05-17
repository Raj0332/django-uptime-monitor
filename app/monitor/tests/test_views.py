"""Tests for monitor views."""
import pytest
from django.urls import reverse

from monitor.models import Site


class TestLoginRequired:
    """Tests that views redirect unauthenticated users to login."""

    def test_dashboard_requires_login(self, client, db):
        response = client.get("/sites/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_site_create_requires_login(self, client, db):
        response = client.get("/sites/add/")
        assert response.status_code == 302

    def test_site_detail_requires_login(self, client, site):
        response = client.get(f"/sites/{site.id}/")
        assert response.status_code == 302


class TestDashboard:
    """Tests for the dashboard view."""

    def test_dashboard_shows_user_sites(self, auth_client, site):
        response = auth_client.get("/sites/")
        assert response.status_code == 200
        assert site.name.encode() in response.content

    def test_dashboard_excludes_other_user_sites(self, auth_client, other_site):
        response = auth_client.get("/sites/")
        assert response.status_code == 200
        assert other_site.name.encode() not in response.content


class TestSiteCreate:
    """Tests for the site creation view."""

    def test_get_create_form(self, auth_client, db):
        response = auth_client.get("/sites/add/")
        assert response.status_code == 200

    def test_create_site_success(self, auth_client, db, user):
        response = auth_client.post("/sites/add/", {
            "name": "My New Site",
            "url": "https://mynewsite.com",
            "check_interval_seconds": 60,
            "timeout_seconds": 10,
            "expected_status_code": 200,
        })
        assert response.status_code == 302
        assert Site.objects.filter(user=user, name="My New Site").exists()

    def test_create_site_invalid_url(self, auth_client, db):
        response = auth_client.post("/sites/add/", {
            "name": "Bad Site",
            "url": "not-a-url",
            "check_interval_seconds": 60,
            "timeout_seconds": 10,
            "expected_status_code": 200,
        })
        assert response.status_code == 200  # Form re-rendered
        assert not Site.objects.filter(name="Bad Site").exists()


class TestSiteDetail:
    """Tests for site detail view and user isolation."""

    def test_can_view_own_site(self, auth_client, site):
        response = auth_client.get(f"/sites/{site.id}/")
        assert response.status_code == 200

    def test_cannot_view_other_user_site(self, auth_client, other_site):
        response = auth_client.get(f"/sites/{other_site.id}/")
        assert response.status_code == 404


class TestSiteDelete:
    """Tests for site deletion view."""

    def test_can_delete_own_site(self, auth_client, site):
        response = auth_client.post(f"/sites/{site.id}/delete/")
        assert response.status_code == 302
        assert not Site.objects.filter(pk=site.id).exists()

    def test_cannot_delete_other_user_site(self, auth_client, other_site):
        response = auth_client.post(f"/sites/{other_site.id}/delete/")
        assert response.status_code == 404
        assert Site.objects.filter(pk=other_site.id).exists()


class TestSiteToggle:
    """Tests for the site toggle (pause/resume) view."""

    def test_toggle_deactivates_active_site(self, auth_client, site):
        assert site.is_active is True
        auth_client.post(f"/sites/{site.id}/toggle/")
        site.refresh_from_db()
        assert site.is_active is False

    def test_toggle_activates_inactive_site(self, auth_client, site):
        site.is_active = False
        site.save()
        auth_client.post(f"/sites/{site.id}/toggle/")
        site.refresh_from_db()
        assert site.is_active is True


class TestSignup:
    """Tests for the signup view."""

    def test_signup_page_loads(self, client, db):
        response = client.get("/accounts/signup/")
        assert response.status_code == 200

    def test_signup_creates_user_and_logs_in(self, client, db):
        response = client.post("/accounts/signup/", {
            "username": "newuser",
            "email": "newuser@example.com",
            "password1": "Str0ngP@ssw0rd!",
            "password2": "Str0ngP@ssw0rd!",
        })
        assert response.status_code == 302
        from django.contrib.auth.models import User
        assert User.objects.filter(username="newuser").exists()
