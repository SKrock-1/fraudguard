"""
Phase 5 — Real-time Alert Layer Tests

Acceptance criteria:
- Using Channels' WebsocketCommunicator, a test creates a high-risk
  transaction and asserts a message is received on a connected consumer.
- Only analyst and admin roles may connect to the alert stream.
- Unauthenticated and ingestion_client users are rejected.
"""
from datetime import timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken
from asgiref.sync import sync_to_async

from fraudguard.asgi import application
from accounts.models import User
from accounts.factories import UserFactory, AccountFactory
from transactions.factories import TransactionFactory
from transactions.models import Transaction
from alerts.models import Alert
from risk.tasks import score_transaction


@pytest.fixture
def analyst_token(db):
    user = UserFactory(username="analyst_user", role=User.Role.ANALYST)
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), user


@pytest.fixture
def admin_token(db):
    user = UserFactory(username="admin_user", role=User.Role.ADMIN)
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), user


@pytest.fixture
def ingestion_token(db):
    user = UserFactory(username="ingestion_user", role=User.Role.INGESTION_CLIENT)
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), user


@sync_to_async
def create_high_risk_transaction():
    now = timezone.now()
    account = AccountFactory(
        avg_spend=Decimal("50.00"),
        spend_stddev=Decimal("10.00"),
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now - timedelta(minutes=5),
    )
    txn = TransactionFactory(
        account=account,
        amount=Decimal("5000.00"),
        lat=Decimal("51.5074"),
        lng=Decimal("-0.1278"),
        timestamp=now,
        status=Transaction.Status.PENDING,
    )
    return txn


@sync_to_async
def create_low_risk_transaction():
    now = timezone.now()
    account = AccountFactory(
        avg_spend=Decimal("100.00"),
        spend_stddev=Decimal("30.00"),
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now - timedelta(hours=2),
    )
    txn = TransactionFactory(
        account=account,
        amount=Decimal("80.00"),
        lat=Decimal("40.7150"),
        lng=Decimal("-74.0050"),
        timestamp=now,
        status=Transaction.Status.PENDING,
    )
    return txn


@sync_to_async
def execute_score_transaction(txn_id: int):
    return score_transaction(txn_id)


@pytest.mark.django_db(transaction=True)
class TestAlertConsumerAuthentication:
    """Test connection gating by role and authentication."""

    async def test_analyst_can_connect_with_jwt_token(self, analyst_token):
        token, user = analyst_token
        communicator = WebsocketCommunicator(application, f"/ws/alerts/?token={token}")
        connected, subprotocol = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    async def test_admin_can_connect_with_jwt_token(self, admin_token):
        token, user = admin_token
        communicator = WebsocketCommunicator(application, f"/ws/alerts/?token={token}")
        connected, subprotocol = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    async def test_unauthenticated_connection_rejected(self):
        communicator = WebsocketCommunicator(application, "/ws/alerts/")
        connected, subprotocol = await communicator.connect()
        assert connected is False

    async def test_ingestion_client_role_rejected(self, ingestion_token):
        token, user = ingestion_token
        communicator = WebsocketCommunicator(application, f"/ws/alerts/?token={token}")
        connected, subprotocol = await communicator.connect()
        assert connected is False


@pytest.mark.django_db(transaction=True)
class TestRealTimeAlertBroadcasting:
    """
    Acceptance criterion: Using Channels' WebsocketCommunicator, a test creates
    a high-risk transaction and asserts a message is received on a connected consumer.
    """

    async def test_high_risk_transaction_broadcasts_alert_to_connected_consumer(
        self, analyst_token, fake_redis
    ):
        token, analyst = analyst_token

        # 1. Connect analyst consumer to the WebSocket stream
        communicator = WebsocketCommunicator(application, f"/ws/alerts/?token={token}")
        connected, _ = await communicator.connect()
        assert connected is True

        # 2. Setup high-risk transaction: NYC -> London in 5 minutes + 500x average spend
        txn = await create_high_risk_transaction()

        # 3. Score the transaction (triggers rule engine + ML scorer + alert broadcast)
        result = await execute_score_transaction(txn.id)
        assert result["status"] == "scored"
        assert result["composite_score"] >= 0.60
        assert result["alert_created"] is True

        # 4. Verify Alert record exists in database
        alert = await Alert.objects.filter(transaction=txn).afirst()
        assert alert is not None
        assert alert.status == Alert.Status.PENDING

        # 5. Assert alert message is pushed to connected WebSocket client
        message = await communicator.receive_json_from(timeout=5)
        assert message["id"] == alert.id
        assert message["transaction_id"] == txn.id
        assert message["idempotency_key"] == txn.idempotency_key
        assert float(message["composite_score"]) >= 0.60
        assert message["status"] == "pending"
        assert "factors" in message
        assert "triggered_rules" in message["factors"]

        await communicator.disconnect()

    async def test_low_risk_transaction_does_not_broadcast_alert(
        self, analyst_token, fake_redis
    ):
        token, analyst = analyst_token

        communicator = WebsocketCommunicator(application, f"/ws/alerts/?token={token}")
        connected, _ = await communicator.connect()
        assert connected is True

        # Benign transaction: normal amount, normal location
        txn = await create_low_risk_transaction()

        result = await execute_score_transaction(txn.id)
        assert result["status"] == "scored"
        assert result["composite_score"] < 0.60

        # No alert record should be created
        alert_exists = await Alert.objects.filter(transaction=txn).aexists()
        assert alert_exists is False

        # Consumer should not receive any message
        assert await communicator.receive_nothing(timeout=1) is True

        await communicator.disconnect()
