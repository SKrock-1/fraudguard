"""Backtest endpoint: threshold sweep on synthetic data and on analyst labels."""
from decimal import Decimal

import pytest

from accounts.factories import AccountFactory
from alerts.models import Alert
from risk.models import RiskScore
from transactions.factories import TransactionFactory


def _score(account, value, alert_status=None):
    txn = TransactionFactory(account=account, amount=Decimal("10.00"))
    rs = RiskScore.objects.create(transaction=txn, composite_score=value, factors={})
    if alert_status:
        Alert.objects.create(transaction=txn, risk_score=rs, status=alert_status)


def test_synthetic_backtest_matches_script(auth_analyst_client):
    r = auth_analyst_client.get("/api/ml/backtest/?source=synthetic")
    assert r.status_code == 200
    assert r.data["samples"] == 250 and r.data["fraud"] == 50
    assert r.data["current_threshold"] == 0.6
    assert r.data["current"]["threshold"] == 0.6
    assert len(r.data["histogram"]) == 20
    assert sum(b["fraud"] + b["legit"] for b in r.data["histogram"]) == 250
    thresholds = [row["threshold"] for row in r.data["thresholds"]]
    assert thresholds == sorted(thresholds)


def test_analyst_backtest_uses_review_labels(auth_analyst_client):
    account = AccountFactory()
    for v in (0.1, 0.2, 0.3, 0.4):
        _score(account, v)
    _score(account, 0.9, Alert.Status.REJECTED)
    _score(account, 0.8, Alert.Status.REJECTED)
    _score(account, 0.7, Alert.Status.APPROVED)
    _score(account, 0.95, Alert.Status.PENDING)  # unreviewed: excluded
    r = auth_analyst_client.get("/api/ml/backtest/?source=analyst")
    assert r.status_code == 200
    d = r.data
    assert (d["samples"], d["fraud"], d["legit"], d["reviewed"]) == (7, 2, 5, 3)
    cur = d["current"]  # threshold 0.6: flags 0.7, 0.8, 0.9
    assert (cur["tp"], cur["fp"], cur["fn"]) == (2, 1, 0)
    assert d["best_f1"]["f1"] == 1.0  # 0.75-0.80 separates perfectly


def test_backtest_rejects_unknown_source(auth_analyst_client):
    assert auth_analyst_client.get("/api/ml/backtest/?source=nope").status_code == 400


def test_backtest_requires_analyst(auth_ingestion_client):
    assert auth_ingestion_client.get("/api/ml/backtest/").status_code == 403
