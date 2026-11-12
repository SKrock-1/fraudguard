"""
Phase 6 — Review Workflow + Insert-Only Audit Log Tests

Acceptance criteria:
- POST /api/alerts/{id}/review/ accepts approve/reject, restricted to analyst/admin roles.
- On review, updates the Alert and writes an audit.AuditLog row.
- A test attempts to update an existing AuditLog row directly and asserts
  it fails at the database level (not just via application logic).
"""
from decimal import Decimal
import pytest
from django.db import connection, DatabaseError, OperationalError
from django.core.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from accounts.factories import UserFactory, AccountFactory
from transactions.factories import TransactionFactory
from risk.models import RiskScore
from alerts.models import Alert
from audit.models import AuditLog


@pytest.fixture
def analyst_client(db):
    user = UserFactory(username="analyst_jane", role=User.Role.ANALYST)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def admin_client(db):
    user = UserFactory(username="admin_bob", role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def ingestion_client(db):
    user = UserFactory(username="api_client_1", role=User.Role.INGESTION_CLIENT)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def pending_alert(db):
    account = AccountFactory()
    txn = TransactionFactory(account=account, amount=Decimal("1200.00"))
    risk = RiskScore.objects.create(
        transaction=txn,
        composite_score=0.85,
        model_version="rules_v1+isoforest_v1",
        factors={"triggered_rules": ["amount_anomaly"], "ml_score": 0.8},
    )
    alert = Alert.objects.create(
        transaction=txn,
        risk_score=risk,
        status=Alert.Status.PENDING,
    )
    return alert


@pytest.mark.django_db
class TestAlertReviewWorkflow:
    """Test the review API endpoint permissions and state transitions."""

    def test_analyst_can_approve_alert(self, analyst_client, pending_alert):
        client, analyst = analyst_client
        url = f"/api/alerts/{pending_alert.id}/review/"
        payload = {
            "decision": "approved",
            "notes": "Verified transaction with customer via phone.",
        }

        response = client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        pending_alert.refresh_from_db()
        assert pending_alert.status == Alert.Status.APPROVED
        assert pending_alert.assigned_to == analyst
        assert pending_alert.resolved_at is not None
        assert "Verified" in pending_alert.notes

        # Verify AuditLog was written
        log = AuditLog.objects.filter(target=f"Alert:{pending_alert.id}").first()
        assert log is not None
        assert log.actor == analyst
        assert log.action == "alert_approved"
        assert log.payload["decision"] == "approved"
        assert log.payload["previous_status"] == Alert.Status.PENDING
        assert log.payload["new_status"] == Alert.Status.APPROVED
        assert log.payload["transaction_id"] == pending_alert.transaction.id

    def test_analyst_can_reject_alert(self, analyst_client, pending_alert):
        client, analyst = analyst_client
        url = f"/api/alerts/{pending_alert.id}/review/"
        payload = {
            "decision": "rejected",
            "notes": "Confirmed compromised card credentials.",
        }

        response = client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        pending_alert.refresh_from_db()
        assert pending_alert.status == Alert.Status.REJECTED
        assert pending_alert.assigned_to == analyst

        log = AuditLog.objects.filter(target=f"Alert:{pending_alert.id}").first()
        assert log is not None
        assert log.action == "alert_rejected"
        assert log.payload["decision"] == "rejected"

    def test_decision_is_final(self, analyst_client, admin_client, pending_alert):
        """A reviewed alert can't be flipped: 409, status unchanged, no second audit row."""
        client, analyst = analyst_client
        url = f"/api/alerts/{pending_alert.id}/review/"
        assert client.post(url, {"decision": "rejected"}, format="json").status_code == status.HTTP_200_OK

        other, _ = admin_client
        response = other.post(url, {"decision": "approved"}, format="json")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already reviewed" in response.data["detail"]
        assert response.data["alert"]["status"] == Alert.Status.REJECTED

        pending_alert.refresh_from_db()
        assert pending_alert.status == Alert.Status.REJECTED
        assert pending_alert.assigned_to == analyst
        assert AuditLog.objects.filter(target=f"Alert:{pending_alert.id}").count() == 1

    def test_admin_can_review_alert(self, admin_client, pending_alert):
        client, admin = admin_client
        url = f"/api/alerts/{pending_alert.id}/review/"
        response = client.post(url, {"decision": "approved"}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_ingestion_client_cannot_review_alerts(self, ingestion_client, pending_alert):
        client, _ = ingestion_client
        url = f"/api/alerts/{pending_alert.id}/review/"
        response = client.post(url, {"decision": "approved"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_request_rejected(self, pending_alert):
        client = APIClient()
        url = f"/api/alerts/{pending_alert.id}/review/"
        response = client.post(url, {"decision": "approved"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_decision_choice_rejected(self, analyst_client, pending_alert):
        client, _ = analyst_client
        url = f"/api/alerts/{pending_alert.id}/review/"
        response = client.post(url, {"decision": "invalid_choice"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# Not transaction=True: that flushes tables with DELETE between tests, which the
# insert-only triggers correctly reject. Rollback-based isolation works instead.
@pytest.mark.django_db
class TestAuditLogInsertOnlyEnforcement:
    """
    Acceptance criterion: A test attempts to update an existing AuditLog row directly
    and asserts it fails at the database level (not just via application logic).
    """

    def test_database_level_blocks_direct_sql_update(self, db):
        """
        Executing a direct SQL UPDATE on the database connection (completely bypassing
        Django model methods) MUST fail at the database engine level.
        """
        log = AuditLog.objects.create(
            action="alert_approved",
            target="Alert:999",
            payload={"initial": True},
        )

        with pytest.raises((DatabaseError, OperationalError)) as exc_info:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_auditlog SET action = 'tampered' WHERE id = %s",
                    [log.id],
                )

        error_message = str(exc_info.value).lower()
        assert any(term in error_message for term in ["insert-only", "permission", "disallowed", "abort"])

    def test_database_level_blocks_queryset_update(self, db):
        """
        QuerySet.update() produces an UPDATE statement directly in SQL, bypassing
        model .save(). The database engine must reject it.
        """
        log = AuditLog.objects.create(
            action="alert_approved",
            target="Alert:888",
            payload={"initial": True},
        )

        with pytest.raises((DatabaseError, OperationalError)):
            AuditLog.objects.filter(id=log.id).update(action="tampered")

    def test_database_level_blocks_direct_sql_delete(self, db):
        """
        A direct SQL DELETE (bypassing model .delete()) MUST fail at the database level.
        """
        log = AuditLog.objects.create(
            action="alert_rejected",
            target="Alert:777",
            payload={"initial": True},
        )

        with pytest.raises((DatabaseError, OperationalError)) as exc_info:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [log.id])

        assert "insert-only" in str(exc_info.value).lower()

    def test_database_level_blocks_queryset_delete(self, db):
        """
        QuerySet.delete() skips the model's delete() guard; the database must reject it.
        """
        log = AuditLog.objects.create(
            action="alert_rejected",
            target="Alert:776",
            payload={"initial": True},
        )

        with pytest.raises((DatabaseError, OperationalError)):
            AuditLog.objects.filter(id=log.id).delete()


    def test_model_level_guards_block_mutation(self, db):
        """
        Application-level guards (.save() on existing instance and .delete())
        raise PermissionDenied as defense-in-depth.
        """
        log = AuditLog.objects.create(
            action="alert_approved",
            target="Alert:666",
            payload={"initial": True},
        )

        with pytest.raises(PermissionDenied):
            log.action = "modified"
            log.save()

        with pytest.raises(PermissionDenied):
            log.delete()
