"""
Dashboard support endpoints: aggregate stats, the demo traffic simulator and
the seed_demo management command.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AccountFactory, UserFactory
from accounts.models import User
from alerts.models import Alert
from risk.tasks import score_transaction
from transactions.factories import TransactionFactory
from transactions.models import Transaction


def _client(role):
    user = UserFactory(role=role, username=f"dash_{role}")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def scored_history(fake_redis):
    now = timezone.now()
    account = AccountFactory(
        avg_spend=Decimal("50.00"),
        spend_stddev=Decimal("10.00"),
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now - timedelta(hours=3),
    )
    normal = TransactionFactory(account=account, amount=Decimal("52.00"), timestamp=now - timedelta(hours=2))
    score_transaction(normal.id)
    # Tokyo, 30 minutes later, 100x normal spend -> travel + amount -> alert
    fraud = TransactionFactory(
        account=account, amount=Decimal("5000.00"),
        lat=Decimal("35.6762"), lng=Decimal("139.6503"),
        timestamp=now - timedelta(hours=1, minutes=30),
    )
    score_transaction(fraud.id)
    return normal, fraud


class TestAlertStats:
    def test_totals_series_histogram_and_rules(self, scored_history):
        resp = _client(User.Role.ANALYST).get("/api/alerts/stats/?window=24h")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert data["totals"]["transactions"] == 2
        assert data["totals"]["scored"] == 2
        assert data["totals"]["alerts"] == 1
        assert data["totals"]["pending"] == 1
        assert data["totals"]["alert_rate"] == 0.5
        assert Decimal(data["totals"]["flagged_amount"]) == Decimal("5000.00")

        assert len(data["series"]) in (24, 25)
        assert sum(b["transactions"] for b in data["series"]) == 2
        assert sum(b["alerts"] for b in data["series"]) == 1

        assert len(data["score_histogram"]) == 20
        assert sum(b["count"] for b in data["score_histogram"]) == 2

        rules = {r["rule"]: r["count"] for r in data["rule_triggers"]}
        assert rules["impossible_travel"] == 1
        assert rules["amount_anomaly"] == 1

    def test_excludes_transactions_outside_window(self, scored_history):
        data = _client(User.Role.ANALYST).get("/api/alerts/stats/?window=1h").json()
        assert data["totals"]["transactions"] == 0
        assert len(data["series"]) in (60, 61)

    def test_invalid_window_rejected(self):
        resp = _client(User.Role.ANALYST).get("/api/alerts/stats/?window=1y")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_ingestion_client_denied(self):
        resp = _client(User.Role.INGESTION_CLIENT).get("/api/alerts/stats/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestSimulateTraffic:
    def test_starts_stream_when_enabled(self, settings):
        settings.DEMO_TOOLS_ENABLED = True
        with patch("risk.simulator.start_live_stream", return_value=True) as start:
            resp = _client(User.Role.ANALYST).post(
                "/api/demo/simulate/", {"count": 5, "fraud_rate": 0.5}, format="json"
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        start.assert_called_once_with(count=5, fraud_rate=0.5, duration_seconds=30.0)

    def test_conflict_when_already_running(self, settings):
        settings.DEMO_TOOLS_ENABLED = True
        with patch("risk.simulator.start_live_stream", return_value=False):
            resp = _client(User.Role.ANALYST).post("/api/demo/simulate/", {}, format="json")
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_disabled_returns_403(self, settings):
        settings.DEMO_TOOLS_ENABLED = False
        resp = _client(User.Role.ADMIN).post("/api/demo/simulate/", {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_ingestion_client_denied(self, settings):
        settings.DEMO_TOOLS_ENABLED = True
        resp = _client(User.Role.INGESTION_CLIENT).post("/api/demo/simulate/", {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_run_live_stream_creates_and_scores(self, fake_redis, monkeypatch):
        from risk import simulator
        # In production this runs on its own thread, where recycling connections is
        # right; inline inside the test's transaction it would close the test's own
        # connection once it is older than CONN_MAX_AGE (slow runs against Postgres).
        monkeypatch.setattr(simulator, "close_old_connections", lambda: None)
        AccountFactory()
        simulator.run_live_stream(count=3, fraud_rate=0.0, duration_seconds=0.01)
        assert Transaction.objects.count() == 3
        assert not Transaction.objects.filter(status=Transaction.Status.PENDING).exists()


class TestSeedDemo:
    def test_requires_password(self, monkeypatch):
        monkeypatch.delenv("DEMO_PASSWORD", raising=False)
        with pytest.raises(CommandError):
            call_command("seed_demo", "--events", "5")

    def test_seeds_users_accounts_and_scored_history(self, fake_redis, monkeypatch):
        monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")
        call_command("seed_demo", "--accounts", "6", "--events", "60", "--fraud-rate", "0.3", "--seed", "7")

        analyst = User.objects.get(username="maya.chen")
        assert analyst.role == User.Role.ANALYST
        assert analyst.check_password("test-only-password")
        assert Transaction.objects.count() >= 60
        assert not Transaction.objects.filter(status=Transaction.Status.PENDING).exists()
        assert Alert.objects.exists()

    def test_refuses_to_double_seed_without_reset(self, fake_redis, monkeypatch):
        monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")
        call_command("seed_demo", "--accounts", "2", "--events", "5")
        with pytest.raises(CommandError):
            call_command("seed_demo", "--accounts", "2", "--events", "5")


class TestAuditLogList:
    def test_lists_newest_first_and_filters_by_target(self):
        from audit.models import AuditLog
        AuditLog.objects.create(action="alert_approved", target="Alert:1", payload={})
        AuditLog.objects.create(action="alert_rejected", target="Alert:2", payload={})
        client = _client(User.Role.ANALYST)

        rows = client.get("/api/audit/").json()
        assert [r["target"] for r in rows] == ["Alert:2", "Alert:1"]

        rows = client.get("/api/audit/?target=Alert:1").json()
        assert [r["action"] for r in rows] == ["alert_approved"]

    def test_ingestion_client_denied(self):
        resp = _client(User.Role.INGESTION_CLIENT).get("/api/audit/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_seed_keep_passwords_leaves_existing_logins(fake_redis, monkeypatch):
    from accounts.factories import UserFactory
    existing = UserFactory(username="maya.chen", role=User.Role.ANALYST)
    existing.set_password("set-by-render")
    existing.save()
    monkeypatch.setenv("DEMO_PASSWORD", "local-throwaway")
    call_command("seed_demo", "--accounts", "3", "--events", "10", "--keep-passwords", "--seed", "3")
    existing.refresh_from_db()
    assert existing.check_password("set-by-render")
    assert User.objects.get(username="dev.patel").check_password("local-throwaway")  # newly created
