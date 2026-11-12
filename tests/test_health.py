"""
Phase 9 — Health check endpoint used by Render / docker compose / UptimeRobot.
"""
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient


def test_health_ok_without_auth(fake_redis):
    resp = APIClient().get("/api/health/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_health_returns_503_when_redis_down(fake_redis):
    with patch.object(fake_redis, "ping", side_effect=ConnectionError("down")):
        resp = APIClient().get("/api/health/")
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert resp.json()["checks"]["redis"] == "error"


def test_health_worker_check_reports_eager_in_tests(fake_redis):
    resp = APIClient().get("/api/health/?worker=1")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["checks"]["worker"] == "eager"


def test_health_worker_check_fails_when_no_worker_replies(fake_redis, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    with patch("fraudguard.celery.app.control.ping", return_value=[]):
        resp = APIClient().get("/api/health/?worker=1")
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert resp.json()["checks"]["worker"] == "error"
