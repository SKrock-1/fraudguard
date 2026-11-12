import uuid
from decimal import Decimal
import pytest
from rest_framework import status
from transactions.models import Transaction
from transactions.factories import TransactionFactory


def test_idempotent_ingestion_success(auth_ingestion_client, test_account):
    """
    Test that creating a new transaction returns 202 Accepted,
    and submitting the same idempotency_key again returns 200 OK
    with exactly one Transaction record in the database.
    """
    idempotency_key = f"idemp_{uuid.uuid4()}"
    payload = {
        "account_number": test_account.account_number,
        "amount": "149.50",
        "currency": "USD",
        "merchant": "BestBuy Online",
        "lat": "40.712800",
        "lng": "-74.006000",
        "idempotency_key": idempotency_key,
    }

    # First submission: new transaction -> 202 Accepted
    response1 = auth_ingestion_client.post("/api/transactions/", payload, format="json")
    assert response1.status_code == status.HTTP_202_ACCEPTED
    assert response1.data["idempotency_key"] == idempotency_key
    assert response1.data["status"] == "pending"
    assert response1.data["amount"] == "149.50"
    first_id = response1.data["id"]

    # Exactly 1 row in DB
    assert Transaction.objects.filter(idempotency_key=idempotency_key).count() == 1

    # Second submission: same idempotency_key -> 200 OK with original data
    response2 = auth_ingestion_client.post("/api/transactions/", payload, format="json")
    assert response2.status_code == status.HTTP_200_OK
    assert response2.data["id"] == first_id
    assert response2.data["idempotency_key"] == idempotency_key

    # Still exactly 1 row in DB
    assert Transaction.objects.filter(idempotency_key=idempotency_key).count() == 1


def test_unauthenticated_request_rejected(api_client, test_account):
    """
    Test that unauthenticated requests to the ingestion endpoint are rejected with 401.
    """
    payload = {
        "account_number": test_account.account_number,
        "amount": "50.00",
        "merchant": "Target",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = api_client.post("/api/transactions/", payload, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert Transaction.objects.count() == 0


def test_analyst_role_cannot_ingest_transactions(auth_analyst_client, test_account):
    """
    Test that an analyst user cannot post transactions (403 Forbidden).
    Only ingestion_client or admin are permitted.
    """
    payload = {
        "account_number": test_account.account_number,
        "amount": "75.00",
        "merchant": "Walmart",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = auth_analyst_client.post("/api/transactions/", payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_role_can_ingest_transactions(auth_admin_client, test_account):
    """
    Test that an admin user is also permitted to post transactions.
    """
    idempotency_key = f"admin_txn_{uuid.uuid4()}"
    payload = {
        "account_number": test_account.account_number,
        "amount": "120.00",
        "merchant": "Apple Store",
        "idempotency_key": idempotency_key,
    }
    response = auth_admin_client.post("/api/transactions/", payload, format="json")
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert Transaction.objects.filter(idempotency_key=idempotency_key).count() == 1


def test_missing_required_fields(auth_ingestion_client):
    """
    Test validation errors when required fields are missing.
    """
    response = auth_ingestion_client.post("/api/transactions/", {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "account_number" in response.data
    assert "amount" in response.data
    assert "merchant" in response.data
    assert "idempotency_key" in response.data


def test_non_existent_account(auth_ingestion_client):
    """
    Test validation error when account_number does not exist.
    """
    payload = {
        "account_number": "ACC_DOES_NOT_EXIST",
        "amount": "25.00",
        "merchant": "Starbucks",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = auth_ingestion_client.post("/api/transactions/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "account_number" in response.data


def test_invalid_amount(auth_ingestion_client, test_account):
    """
    Test validation error when amount is zero or negative.
    """
    payload = {
        "account_number": test_account.account_number,
        "amount": "-10.00",
        "merchant": "Starbucks",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = auth_ingestion_client.post("/api/transactions/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "amount" in response.data


def test_transaction_factory(test_account):
    """
    Test that the TransactionFactory creates valid Transaction instances.
    """
    txn = TransactionFactory(account=test_account, amount=Decimal("250.00"))
    assert txn.id is not None
    assert txn.account == test_account
    assert txn.amount == Decimal("250.00")
    assert txn.status == Transaction.Status.PENDING
