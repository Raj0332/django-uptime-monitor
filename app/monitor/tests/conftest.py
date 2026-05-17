"""Shared pytest fixtures for the monitor app tests."""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from monitor.models import Check, Incident, Site


@pytest.fixture
def user(db) -> User:
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpassword123",
    )


@pytest.fixture
def other_user(db) -> User:
    """Create a second test user for isolation tests."""
    return User.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="otherpassword123",
    )


@pytest.fixture
def auth_client(user) -> Client:
    """Return a Django test client logged in as `user`."""
    client = Client()
    client.login(username="testuser", password="testpassword123")
    return client


@pytest.fixture
def site(user, db) -> Site:
    """Create a test site owned by `user`."""
    return Site.objects.create(
        user=user,
        name="Test Site",
        url="https://example.com",
        check_interval_seconds=60,
        timeout_seconds=10,
        expected_status_code=200,
    )


@pytest.fixture
def other_site(other_user, db) -> Site:
    """Create a test site owned by `other_user`."""
    return Site.objects.create(
        user=other_user,
        name="Other Site",
        url="https://other.example.com",
        check_interval_seconds=60,
        timeout_seconds=10,
        expected_status_code=200,
    )


@pytest.fixture
def make_check(db):
    """Factory fixture for creating Check objects."""
    def _make(site: Site, is_up: bool = True, response_time_ms: int = 100,
              status_code: int = 200, error_message: str = "") -> Check:
        return Check.objects.create(
            site=site,
            is_up=is_up,
            response_time_ms=response_time_ms if is_up else None,
            status_code=status_code if is_up else None,
            error_message=error_message,
            timestamp=timezone.now(),
        )
    return _make
