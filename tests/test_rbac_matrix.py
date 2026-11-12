"""
Phase 7 — RBAC Role-Matrix Tests.

Covers every endpoint × every role to assert correct allow/deny behaviour,
as required by FR-9 and the Phase 7 acceptance criteria.

Endpoint inventory:
  POST   /api/auth/token/           — open (login)
  POST   /api/auth/token/refresh/   — open (token refresh)
  GET    /api/auth/me/              — any authenticated
  POST   /api/transactions/         — ingestion_client, admin
  GET    /api/alerts/               — analyst, admin
  GET    /api/alerts/{id}/          — analyst, admin
  POST   /api/alerts/{id}/review/   — analyst, admin

Roles:
  ingestion_client — can only ingest transactions
  analyst          — can view/review alerts, view own profile
  admin            — can do everything
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from accounts.factories import UserFactory, AccountFactory
from transactions.factories import TransactionFactory
from alerts.models import Alert
from risk.models import RiskScore


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def ingestion_user():
    return UserFactory(role=User.Role.INGESTION_CLIENT, username="rbac_ingest")


@pytest.fixture
def analyst_user():
    return UserFactory(role=User.Role.ANALYST, username="rbac_analyst")


@pytest.fixture
def admin_user():
    return UserFactory(role=User.Role.ADMIN, username="rbac_admin")


def _auth_client(user):
    """Return an APIClient force-authenticated as the given user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def sample_account(ingestion_user):
    return AccountFactory(
        user=ingestion_user,
        account_number="RBAC_ACC_001",
        avg_spend=Decimal("100.00"),
        spend_stddev=Decimal("10.00"),
    )


@pytest.fixture
def sample_alert(sample_account):
    """Create a transaction → risk score → alert chain for review tests."""
    txn = TransactionFactory(account=sample_account, idempotency_key="rbac_txn_001")
    risk = RiskScore.objects.create(
        transaction=txn,
        composite_score=0.85,
        model_version="test",
        factors={"test": True},
    )
    alert = Alert.objects.create(
        transaction=txn,
        risk_score=risk,
        status=Alert.Status.PENDING,
    )
    return alert


def _ingest_payload(account):
    return {
        "account_number": account.account_number,
        "amount": "250.00",
        "currency": "USD",
        "merchant": "RBAC Test Merchant",
        "idempotency_key": f"rbac_key_{timezone.now().timestamp()}",
    }


# ─── /api/auth/me/ — Any authenticated user ──────────────────────────────────

class TestCurrentUserEndpoint:
    """GET /api/auth/me/ — accessible by any authenticated role."""

    def test_ingestion_client_can_access_me(self, ingestion_user):
        resp = _auth_client(ingestion_user).get("/api/auth/me/")
        assert resp.status_code == status.HTTP_200_OK

    def test_analyst_can_access_me(self, analyst_user):
        resp = _auth_client(analyst_user).get("/api/auth/me/")
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_access_me(self, admin_user):
        resp = _auth_client(admin_user).get("/api/auth/me/")
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated_cannot_access_me(self):
        resp = APIClient().get("/api/auth/me/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ─── POST /api/transactions/ — ingestion_client & admin only ──────────────────

class TestTransactionIngestionRBAC:
    """POST /api/transactions/ — only ingestion_client and admin roles."""

    def test_ingestion_client_can_ingest(self, ingestion_user, sample_account):
        resp = _auth_client(ingestion_user).post(
            "/api/transactions/",
            _ingest_payload(sample_account),
            format="json",
        )
        assert resp.status_code in (
            status.HTTP_202_ACCEPTED,
            status.HTTP_200_OK,
        )

    def test_admin_can_ingest(self, admin_user, sample_account):
        payload = _ingest_payload(sample_account)
        payload["idempotency_key"] = "admin_ingest_rbac_key"
        resp = _auth_client(admin_user).post(
            "/api/transactions/", payload, format="json",
        )
        assert resp.status_code in (
            status.HTTP_202_ACCEPTED,
            status.HTTP_200_OK,
        )

    def test_analyst_cannot_ingest(self, analyst_user, sample_account):
        resp = _auth_client(analyst_user).post(
            "/api/transactions/",
            _ingest_payload(sample_account),
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_ingest(self, sample_account):
        resp = APIClient().post(
            "/api/transactions/",
            _ingest_payload(sample_account),
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ─── GET /api/alerts/ — analyst & admin only ──────────────────────────────────

class TestAlertListRBAC:
    """GET /api/alerts/ — only analyst and admin roles."""

    def test_analyst_can_list_alerts(self, analyst_user, sample_alert):
        resp = _auth_client(analyst_user).get("/api/alerts/")
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_list_alerts(self, admin_user, sample_alert):
        resp = _auth_client(admin_user).get("/api/alerts/")
        assert resp.status_code == status.HTTP_200_OK

    def test_ingestion_client_cannot_list_alerts(self, ingestion_user, sample_alert):
        resp = _auth_client(ingestion_user).get("/api/alerts/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_list_alerts(self, sample_alert):
        resp = APIClient().get("/api/alerts/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ─── GET /api/alerts/{id}/ — analyst & admin only ─────────────────────────────

class TestAlertDetailRBAC:
    """GET /api/alerts/{id}/ — only analyst and admin roles."""

    def test_analyst_can_view_alert_detail(self, analyst_user, sample_alert):
        resp = _auth_client(analyst_user).get(f"/api/alerts/{sample_alert.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_view_alert_detail(self, admin_user, sample_alert):
        resp = _auth_client(admin_user).get(f"/api/alerts/{sample_alert.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_ingestion_client_cannot_view_alert_detail(self, ingestion_user, sample_alert):
        resp = _auth_client(ingestion_user).get(f"/api/alerts/{sample_alert.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_view_alert_detail(self, sample_alert):
        resp = APIClient().get(f"/api/alerts/{sample_alert.id}/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ─── POST /api/alerts/{id}/review/ — analyst & admin only ─────────────────────

class TestAlertReviewRBAC:
    """POST /api/alerts/{id}/review/ — only analyst and admin roles."""

    def test_analyst_can_review_alert(self, analyst_user, sample_alert):
        resp = _auth_client(analyst_user).post(
            f"/api/alerts/{sample_alert.id}/review/",
            {"decision": "approved", "notes": "RBAC test"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_review_alert(self, admin_user, sample_alert):
        resp = _auth_client(admin_user).post(
            f"/api/alerts/{sample_alert.id}/review/",
            {"decision": "rejected", "notes": "Admin RBAC test"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_ingestion_client_cannot_review_alert(self, ingestion_user, sample_alert):
        resp = _auth_client(ingestion_user).post(
            f"/api/alerts/{sample_alert.id}/review/",
            {"decision": "approved"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_review_alert(self, sample_alert):
        resp = APIClient().post(
            f"/api/alerts/{sample_alert.id}/review/",
            {"decision": "approved"},
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Throttling tests ─────────────────────────────────────────────────────────

class TestPerClientThrottling:
    """Verify that the ingestion endpoint applies per-client throttling."""

    @pytest.fixture(autouse=True)
    def _clear_throttle_cache(self):
        """Reset DRF's throttle cache between tests."""
        from django.core.cache import cache
        cache.clear()

    def test_throttle_class_is_applied(self, ingestion_user, sample_account):
        """The view should include PerClientIngestionThrottle."""
        from transactions.views import TransactionIngestionView
        from accounts.throttles import PerClientIngestionThrottle
        assert PerClientIngestionThrottle in TransactionIngestionView.throttle_classes

    @pytest.mark.django_db
    def test_throttle_allows_within_limit(self, ingestion_user, sample_account):
        """Requests within the rate limit should be accepted normally."""
        client = _auth_client(ingestion_user)
        # Make a few requests — should be well within 100/minute
        for i in range(3):
            payload = _ingest_payload(sample_account)
            payload["idempotency_key"] = f"throttle_ok_{i}"
            resp = client.post("/api/transactions/", payload, format="json")
            assert resp.status_code in (
                status.HTTP_202_ACCEPTED,
                status.HTTP_200_OK,
            ), f"Request {i} unexpectedly throttled: {resp.status_code}"

    @pytest.mark.django_db
    def test_throttle_enforces_limit(self, sample_account, monkeypatch):
        """When the rate limit is set very low, requests beyond it are rejected with 429."""
        from django.core.cache import cache
        from accounts.throttles import PerClientIngestionThrottle

        cache.clear()
        # DRF reads the rate from THROTTLE_RATES on every throttle instantiation
        monkeypatch.setattr(PerClientIngestionThrottle, "THROTTLE_RATES", {"ingestion": "3/minute"})

        try:
            user = UserFactory(role=User.Role.INGESTION_CLIENT, username="throttle_victim")
            client = _auth_client(user)

            statuses = []
            for i in range(6):
                payload = _ingest_payload(sample_account)
                payload["idempotency_key"] = f"throttle_test_{i}"
                resp = client.post("/api/transactions/", payload, format="json")
                statuses.append(resp.status_code)

            assert statuses[:3].count(status.HTTP_429_TOO_MANY_REQUESTS) == 0, statuses
            assert statuses[3:] == [status.HTTP_429_TOO_MANY_REQUESTS] * 3, statuses
        finally:
            cache.clear()


# ─── Role-matrix summary ─────────────────────────────────────────────────────

ROLE_MATRIX = """
Role-Matrix Coverage:
┌──────────────────────────────────┬───────────────────┬──────────┬─────────┐
│ Endpoint                         │ ingestion_client  │ analyst  │ admin   │
├──────────────────────────────────┼───────────────────┼──────────┼─────────┤
│ GET  /api/auth/me/               │ ✓ ALLOW           │ ✓ ALLOW  │ ✓ ALLOW │
│ POST /api/transactions/          │ ✓ ALLOW           │ ✗ DENY   │ ✓ ALLOW │
│ GET  /api/alerts/                │ ✗ DENY            │ ✓ ALLOW  │ ✓ ALLOW │
│ GET  /api/alerts/{id}/           │ ✗ DENY            │ ✓ ALLOW  │ ✓ ALLOW │
│ POST /api/alerts/{id}/review/    │ ✗ DENY            │ ✓ ALLOW  │ ✓ ALLOW │
└──────────────────────────────────┴───────────────────┴──────────┴─────────┘
+ Unauthenticated → 401 on every endpoint (4 tests)
+ Per-client throttling on ingestion (3 tests)
"""
