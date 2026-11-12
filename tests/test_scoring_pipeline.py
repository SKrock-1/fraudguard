"""
Phase 3 — Async Pipeline Tests

Acceptance criteria:
- With CELERY_TASK_ALWAYS_EAGER=True, creating a transaction results in a
  RiskScore row being created without any additional manual trigger.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status as http_status

from accounts.factories import AccountFactory
from transactions.factories import TransactionFactory
from transactions.models import Transaction
from risk.models import RiskScore
from risk.tasks import score_transaction


class TestScoreTransactionTask:
    """Test the score_transaction Celery task directly."""

    def test_score_transaction_creates_risk_score(self, fake_redis):
        """A pending transaction gets a RiskScore after the task runs."""
        account = AccountFactory(
            avg_spend=Decimal("100.00"),
            spend_stddev=Decimal("20.00"),
        )
        txn = TransactionFactory(
            account=account,
            amount=Decimal("150.00"),
            status=Transaction.Status.PENDING,
        )

        result = score_transaction(txn.id)

        assert result["status"] == "scored"
        assert result["transaction_id"] == txn.id
        assert "composite_score" in result

        # Verify RiskScore was persisted
        risk = RiskScore.objects.get(transaction=txn)
        assert risk.composite_score >= 0.0
        assert "rules_v1" in risk.model_version
        assert "rule_engine" in risk.factors
        assert "triggered_rules" in risk.factors
        assert "composite_breakdown" in risk.factors

        # Verify transaction status was updated
        txn.refresh_from_db()
        assert txn.status == Transaction.Status.SCORED

    def test_score_transaction_idempotent(self, fake_redis):
        """Running the task twice on the same transaction doesn't duplicate or error."""
        account = AccountFactory()
        txn = TransactionFactory(account=account, status=Transaction.Status.PENDING)

        result1 = score_transaction(txn.id)
        assert result1["status"] == "scored"

        result2 = score_transaction(txn.id)
        assert result2["status"] == "skipped"
        assert result2["reason"] == "already_scored"

        # Still exactly one RiskScore
        assert RiskScore.objects.filter(transaction=txn).count() == 1

    def test_score_transaction_nonexistent(self, fake_redis):
        """Task handles a missing transaction gracefully without raising."""
        result = score_transaction(999999)
        assert result["status"] == "error"
        assert result["reason"] == "transaction_not_found"

    def test_score_transaction_high_risk(self, fake_redis):
        """A clearly fraudulent transaction gets a high composite score."""
        now = timezone.now()
        account = AccountFactory(
            avg_spend=Decimal("50.00"),
            spend_stddev=Decimal("10.00"),
            last_known_lat=Decimal("40.7128"),
            last_known_lng=Decimal("-74.0060"),
            last_transaction_at=now - timedelta(minutes=5),
        )
        # Fraudulent: huge amount ($5000, z=495) + impossible travel (NYC → London in 5 min)
        txn = TransactionFactory(
            account=account,
            amount=Decimal("5000.00"),
            lat=Decimal("51.5074"),
            lng=Decimal("-0.1278"),
            timestamp=now,
            status=Transaction.Status.PENDING,
        )

        result = score_transaction(txn.id)
        assert result["status"] == "scored"
        assert result["composite_score"] >= 0.7  # impossible_travel(0.4) + amount_anomaly(0.3) = 0.7

        risk = RiskScore.objects.get(transaction=txn)
        assert risk.factors["composite_breakdown"]["impossible_travel"]["triggered"] is True
        assert risk.factors["composite_breakdown"]["amount_anomaly"]["triggered"] is True
        assert "impossible_travel" in risk.factors["triggered_rules"]
        assert "amount_anomaly" in risk.factors["triggered_rules"]

    def test_score_transaction_low_risk(self, fake_redis):
        """A clearly benign transaction gets a 0.0 composite score."""
        now = timezone.now()
        account = AccountFactory(
            avg_spend=Decimal("100.00"),
            spend_stddev=Decimal("30.00"),
            last_known_lat=Decimal("40.7128"),
            last_known_lng=Decimal("-74.0060"),
            last_transaction_at=now - timedelta(hours=2),
        )
        # Benign: normal amount, same area, hours apart
        txn = TransactionFactory(
            account=account,
            amount=Decimal("90.00"),
            lat=Decimal("40.7300"),
            lng=Decimal("-73.9950"),
            timestamp=now,
            status=Transaction.Status.PENDING,
        )

        result = score_transaction(txn.id)
        assert result["status"] == "scored"
        assert result["composite_score"] == 0.0
        assert result["triggered_rules"] == []


class TestIngestionTriggersScoring:
    """
    Acceptance criterion: With CELERY_TASK_ALWAYS_EAGER=True, a test asserts
    that creating a transaction results in a RiskScore row being created
    without any additional manual trigger.
    """

    def test_ingestion_automatically_scores(self, auth_ingestion_client, test_account, fake_redis):
        """
        POST to the ingestion endpoint -> transaction created -> Celery task
        fires eagerly -> RiskScore row exists, all with no manual trigger.
        """
        idempotency_key = f"auto_score_{uuid.uuid4()}"
        payload = {
            "account_number": test_account.account_number,
            "amount": "200.00",
            "currency": "USD",
            "merchant": "Test Merchant",
            "lat": "40.7128",
            "lng": "-74.0060",
            "idempotency_key": idempotency_key,
        }

        response = auth_ingestion_client.post("/api/transactions/", payload, format="json")
        assert response.status_code == http_status.HTTP_202_ACCEPTED

        txn_id = response.data["id"]

        # The RiskScore should already exist because CELERY_TASK_ALWAYS_EAGER=True
        txn = Transaction.objects.get(id=txn_id)
        assert txn.status == Transaction.Status.SCORED

        risk = RiskScore.objects.get(transaction_id=txn_id)
        assert risk.composite_score >= 0.0
        assert "rules_v1" in risk.model_version
        assert "rule_engine" in risk.factors
        assert "composite_breakdown" in risk.factors

    def test_duplicate_ingestion_does_not_re_score(self, auth_ingestion_client, test_account, fake_redis):
        """
        Submitting the same idempotency_key twice should not create a second RiskScore.
        """
        idempotency_key = f"dup_score_{uuid.uuid4()}"
        payload = {
            "account_number": test_account.account_number,
            "amount": "50.00",
            "merchant": "Dup Merchant",
            "idempotency_key": idempotency_key,
        }

        resp1 = auth_ingestion_client.post("/api/transactions/", payload, format="json")
        assert resp1.status_code == http_status.HTTP_202_ACCEPTED

        resp2 = auth_ingestion_client.post("/api/transactions/", payload, format="json")
        assert resp2.status_code == http_status.HTTP_200_OK

        # Exactly one RiskScore
        assert RiskScore.objects.filter(transaction_id=resp1.data["id"]).count() == 1


class TestMLScoringPipeline:
    """
    Phase 4 — ML scoring tests

    Acceptance criteria:
    - A test with a mocked model asserts the composite score combines both
      rule and ML contributions, and that `factors` is populated.
    """

    def test_mocked_model_combines_rule_and_ml_contributions(self, monkeypatch, fake_redis):
        """
        With a mocked model producing an ML anomaly score (e.g. 0.8),
        assert that:
        1. The composite score combines rule contribution and ML contribution.
        2. `factors` is populated with both rule engine breakdown and ML anomaly score.
        """
        from unittest.mock import MagicMock
        import risk.tasks
        from risk.tasks import score_transaction

        now = timezone.now()
        # Setup account with history
        account = AccountFactory(
            avg_spend=Decimal("100.00"),
            spend_stddev=Decimal("20.00"),
            last_known_lat=Decimal("40.7128"),
            last_known_lng=Decimal("-74.0060"),
            last_transaction_at=now - timedelta(hours=2),
        )

        # Trigger amount anomaly rule: $300 is > 3 stddev from $100 ($100 + 3*20 = $160)
        # amount_anomaly rule weight is 0.30
        txn = TransactionFactory(
            account=account,
            amount=Decimal("300.00"),
            lat=Decimal("40.7130"),
            lng=Decimal("-74.0062"),
            timestamp=now,
            status=Transaction.Status.PENDING,
        )

        # Mock the ML model to return a known anomaly score
        # Isolation Forest: mock decision_function or a mock object with predict_risk
        mock_model = MagicMock()
        mock_model.predict_risk.return_value = 0.80

        monkeypatch.setattr(risk.tasks, "ML_MODEL", mock_model)

        result = score_transaction(txn.id)
        assert result["status"] == "scored"

        # Expected calculation:
        # rule_contribution = 0.30 (amount_anomaly)
        # ml_contribution = 0.80 * 0.30 = 0.24
        # composite_score = min(1.0, 0.30 + 0.24) = 0.54
        assert result["composite_score"] == 0.54
        assert "amount_anomaly" in result["triggered_rules"]

        # Verify persisted RiskScore factors
        risk_score = RiskScore.objects.get(transaction=txn)
        assert risk_score.composite_score == 0.54
        assert risk_score.factors["ml_score"] == 0.80
        assert risk_score.factors["ml_contribution"] == 0.24
        assert "amount_anomaly" in risk_score.factors["triggered_rules"]

        # Verify composite breakdown contains both rule and ML details
        breakdown = risk_score.factors["composite_breakdown"]
        assert breakdown["amount_anomaly"]["triggered"] is True
        assert breakdown["amount_anomaly"]["contribution"] == 0.30
        assert breakdown["ml_anomaly"]["score"] == 0.80
        assert breakdown["ml_anomaly"]["weight"] == 0.30
        assert breakdown["ml_anomaly"]["contribution"] == 0.24

    def test_mocked_model_pure_ml_anomaly(self, monkeypatch, fake_redis):
        """
        When rules do NOT trigger (benign amounts, normal location, no velocity spike),
        an anomalous ML score still flags risk and produces an explainable factor breakdown.
        """
        from unittest.mock import MagicMock
        import risk.tasks
        from risk.tasks import score_transaction

        now = timezone.now()
        account = AccountFactory(
            avg_spend=Decimal("100.00"),
            spend_stddev=Decimal("25.00"),
            last_known_lat=Decimal("40.7128"),
            last_known_lng=Decimal("-74.0060"),
            last_transaction_at=now - timedelta(hours=3),
        )
        # Benign transaction: $95, same location -> no rules trigger
        txn = TransactionFactory(
            account=account,
            amount=Decimal("95.00"),
            lat=Decimal("40.7130"),
            lng=Decimal("-74.0062"),
            timestamp=now,
            status=Transaction.Status.PENDING,
        )

        mock_model = MagicMock()
        mock_model.predict_risk.return_value = 0.90
        monkeypatch.setattr(risk.tasks, "ML_MODEL", mock_model)

        result = score_transaction(txn.id)
        assert result["status"] == "scored"
        # 0.0 rules + (0.90 * 0.30 = 0.27) = 0.27
        assert result["composite_score"] == 0.27
        assert result["triggered_rules"] == []

        risk_score = RiskScore.objects.get(transaction=txn)
        assert risk_score.composite_score == 0.27
        assert risk_score.factors["ml_score"] == 0.90
        assert risk_score.factors["ml_contribution"] == 0.27
        assert risk_score.factors["composite_breakdown"]["ml_anomaly"]["contribution"] == 0.27

    def test_feature_extraction(self):
        """Verify standard 5-feature vector extraction."""
        from risk.ml import extract_features, FEATURE_NAMES
        import numpy as np

        account = AccountFactory.build(
            avg_spend=Decimal("100.00"),
            spend_stddev=Decimal("20.00"),
        )
        txn = TransactionFactory.build(
            account=account,
            amount=Decimal("150.00"),
        )

        features = extract_features(txn, account=account)
        assert isinstance(features, np.ndarray)
        assert features.shape == (1, 5)
        assert len(FEATURE_NAMES) == 5
        # amount=150.0, amount_to_avg=150/101 ~ 1.485, z_score=(150-100)/20 = 2.5
        assert features[0, 0] == 150.0
        assert round(features[0, 4], 2) == 2.50


class TestAccountProfileUpdates:
    """Scoring folds each transaction into the account's rolling profile."""

    def test_rolling_stats_match_population_mean_and_stddev(self, fake_redis):
        import statistics

        account = AccountFactory(avg_spend=Decimal("0.00"), spend_stddev=Decimal("0.00"))
        amounts = [Decimal("10.00"), Decimal("20.00"), Decimal("30.00"), Decimal("100.00")]
        start = timezone.now() - timedelta(hours=4)
        for i, amount in enumerate(amounts):
            txn = TransactionFactory(account=account, amount=amount, timestamp=start + timedelta(hours=i))
            score_transaction(txn.id)

        account.refresh_from_db()
        floats = [float(a) for a in amounts]
        assert float(account.avg_spend) == pytest.approx(statistics.mean(floats), abs=0.01)
        assert float(account.spend_stddev) == pytest.approx(statistics.pstdev(floats), abs=0.02)

    def test_location_and_time_baseline_updated(self, fake_redis):
        account = AccountFactory(last_known_lat=None, last_known_lng=None, last_transaction_at=None)
        ts = timezone.now()
        txn = TransactionFactory(account=account, lat=Decimal("51.507400"), lng=Decimal("-0.127800"), timestamp=ts)

        score_transaction(txn.id)

        account.refresh_from_db()
        assert account.last_known_lat == Decimal("51.507400")
        assert account.last_known_lng == Decimal("-0.127800")
        assert account.last_transaction_at == ts

    def test_out_of_order_transaction_does_not_rewind_location(self, fake_redis):
        now = timezone.now()
        account = AccountFactory(
            last_known_lat=Decimal("40.712800"),
            last_known_lng=Decimal("-74.006000"),
            last_transaction_at=now,
        )
        late_txn = TransactionFactory(
            account=account, lat=Decimal("35.676200"), lng=Decimal("139.650300"),
            timestamp=now - timedelta(days=1),
        )

        score_transaction(late_txn.id)

        account.refresh_from_db()
        assert account.last_known_lat == Decimal("40.712800")
        assert account.last_transaction_at == now

    def test_rescoring_does_not_double_count(self, fake_redis):
        account = AccountFactory(avg_spend=Decimal("0.00"), spend_stddev=Decimal("0.00"))
        txn = TransactionFactory(account=account, amount=Decimal("50.00"))

        score_transaction(txn.id)
        score_transaction(txn.id)  # already scored -> skipped

        account.refresh_from_db()
        assert account.avg_spend == Decimal("50.00")
