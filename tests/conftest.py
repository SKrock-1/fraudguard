import pytest
from rest_framework.test import APIClient
from accounts.models import User
from accounts.factories import UserFactory, AccountFactory
from transactions.factories import TransactionFactory


import fakeredis
from risk.redis_client import set_redis_client


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Ensure database access is enabled for all tests."""
    pass


@pytest.fixture(autouse=True)
def fake_redis():
    """Ensure an isolated in-memory Redis instance is used across all tests."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    set_redis_client(client)
    yield client
    client.flushall()
    set_redis_client(None)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def ingestion_client_user():
    return UserFactory(role=User.Role.INGESTION_CLIENT, username="ingest_svc")


@pytest.fixture
def analyst_user():
    return UserFactory(role=User.Role.ANALYST, username="analyst_jane")


@pytest.fixture
def admin_user():
    return UserFactory(role=User.Role.ADMIN, username="admin_super")


@pytest.fixture
def auth_ingestion_client(api_client, ingestion_client_user):
    api_client.force_authenticate(user=ingestion_client_user)
    return api_client


@pytest.fixture
def auth_analyst_client(api_client, analyst_user):
    api_client.force_authenticate(user=analyst_user)
    return api_client


@pytest.fixture
def auth_admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def test_account(ingestion_client_user):
    return AccountFactory(user=ingestion_client_user, account_number="ACC_TEST_001")
