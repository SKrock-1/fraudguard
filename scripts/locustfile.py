"""
Phase 8 — Locust Load Test for FraudGuard Ingestion Endpoint.

Simulates concurrent API clients POSTing transactions to
POST /api/transactions/ and reports latency / throughput.

Usage:
    # Start a local server first (in another terminal):
    #   python manage.py runserver 0.0.0.0:8000

    # Run headless for 60 seconds with 10 users:
    locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 60s \\
        --host http://localhost:8000

    # Or with the web UI:
    locust -f scripts/locustfile.py --host http://localhost:8000
    # Then open http://localhost:8089 in your browser.

Environment variables (optional):
    LOCUST_USERNAME   — username of an ingestion_client user (default: locust_client)
    LOCUST_PASSWORD   — password for that user (default: locust_password123)
    LOCUST_ACCOUNT    — account_number to use (default: LOCUST_ACC_001)

Setup:
    Before running, create the test user and account:
        python manage.py shell -c "
        from accounts.models import User, Account
        u, _ = User.objects.get_or_create(username='locust_client',
            defaults={'role': 'ingestion_client'})
        u.set_password('locust_password123')
        u.save()
        Account.objects.get_or_create(user=u, account_number='LOCUST_ACC_001',
            defaults={'avg_spend': 100, 'spend_stddev': 30})
        print('Locust user and account ready.')
        "
"""
import os
import uuid
import random
from locust import HttpUser, task, between, events


class FraudGuardIngestionUser(HttpUser):
    """
    Simulates a B2B API client that authenticates via JWT and submits
    transactions at a steady rate.
    """
    wait_time = between(0.1, 0.5)
    host = os.getenv("LOCUST_HOST", "http://localhost:8000")

    # Credentials
    _username = os.getenv("LOCUST_USERNAME", "locust_client")
    _password = os.getenv("LOCUST_PASSWORD", "locust_password123")
    _account = os.getenv("LOCUST_ACCOUNT", "LOCUST_ACC_001")

    def on_start(self):
        """Authenticate and store the JWT access token."""
        resp = self.client.post("/api/auth/token/", json={
            "username": self._username,
            "password": self._password,
        })
        if resp.status_code == 200:
            self._token = resp.json().get("access", "")
            self.client.headers.update({
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            })
        else:
            # Log auth failure but continue — tasks will get 401s
            self._token = ""
            print(f"[WARN] Auth failed ({resp.status_code}): {resp.text[:200]}")

    @task(weight=10)
    def ingest_transaction(self):
        """POST a new transaction with a unique idempotency key."""
        payload = {
            "account_number": self._account,
            "amount": str(round(random.uniform(5.0, 5000.0), 2)),
            "currency": random.choice(["USD", "EUR", "GBP"]),
            "merchant": random.choice([
                "Amazon", "Walmart", "Target", "BestBuy",
                "Starbucks", "McDonalds", "Shell", "BP",
            ]),
            "lat": str(round(40.7128 + random.uniform(-0.1, 0.1), 6)),
            "lng": str(round(-74.0060 + random.uniform(-0.1, 0.1), 6)),
            "idempotency_key": str(uuid.uuid4()),
        }
        self.client.post("/api/transactions/", json=payload, name="POST /api/transactions/")

    @task(weight=2)
    def ingest_duplicate(self):
        """
        POST a transaction and then immediately retry it with the same
        idempotency key to test deduplication under load.
        """
        key = str(uuid.uuid4())
        payload = {
            "account_number": self._account,
            "amount": "42.00",
            "currency": "USD",
            "merchant": "DuplicateTest",
            "idempotency_key": key,
        }
        self.client.post("/api/transactions/", json=payload, name="POST /api/transactions/ (first)")
        self.client.post("/api/transactions/", json=payload, name="POST /api/transactions/ (dupe)")
