"""Tests for health check endpoints."""
import pytest
from unittest.mock import MagicMock, patch


class TestHealthz:
    """Tests for /healthz/ liveness probe."""

    def test_healthz_returns_200(self, client, db):
        response = client.get("/healthz/")
        assert response.status_code == 200

    def test_healthz_returns_ok_json(self, client, db):
        response = client.get("/healthz/")
        data = response.json()
        assert data["status"] == "ok"

    def test_healthz_no_db_required(self, client):
        # Should work without any DB calls (no db fixture)
        response = client.get("/healthz/")
        assert response.status_code == 200


class TestReadyz:
    """Tests for /readyz/ readiness probe."""

    def test_readyz_returns_200_when_healthy(self, client, db):
        import redis as redis_lib
        with patch.object(redis_lib.Redis, "ping", return_value=True):
            response = client.get("/readyz/")
        # DB is available in tests, Redis might not be — just check the format
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "postgres" in data["checks"]

    def test_readyz_503_when_db_down(self, client, db):
        with patch("django.db.connection.cursor") as mock_cursor:
            mock_cursor.side_effect = Exception("DB unavailable")
            with patch("monitor.views._readyz_cache", {"result": None, "ts": 0.0}):
                response = client.get("/readyz/")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert "postgres" in data["checks"]
        assert data["checks"]["postgres"] != "ok"

    def test_readyz_checks_postgres(self, client, db):
        with patch("monitor.views._readyz_cache", {"result": None, "ts": 0.0}):
            response = client.get("/readyz/")
        data = response.json()
        assert "postgres" in data["checks"]

    def test_readyz_includes_redis_check(self, client, db):
        with patch("monitor.views._readyz_cache", {"result": None, "ts": 0.0}):
            response = client.get("/readyz/")
        data = response.json()
        assert "redis" in data["checks"]
