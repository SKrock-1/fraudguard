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



def _set_audit_triggers(enabled: bool):
    from django.db import connection
    with connection.cursor() as c:
        c.execute(f"ALTER TABLE audit_auditlog {'ENABLE' if enabled else 'DISABLE'} TRIGGER USER")


@pytest.fixture(autouse=True)
def _audit_triggers_on_postgres(request, enable_db_access_for_all_tests):
    """
    `transaction=True` tests reset the database with TRUNCATE afterwards, which the
    audit table's insert-only trigger (rightly) refuses on Postgres. So, in the
    throwaway test database only: triggers are switched on at the start of every
    test, and off in a transactional test's teardown, which runs just before
    pytest-django's flush (this fixture depends on the db fixtures, so it is torn
    down first). No-op on SQLite.
    """
    from django.db import connection
    if connection.vendor != "postgresql":
        yield
        return
    _set_audit_triggers(True)
    yield
    marker = request.node.get_closest_marker("django_db")
    if marker and marker.kwargs.get("transaction"):
        _set_audit_triggers(False)
