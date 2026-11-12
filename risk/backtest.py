"""
Detection-quality evaluation shared by scripts/backtest.py and the API.

Two label sources:
  * synthetic  - generated benign/fraud records replayed through the rules + ML
  * analyst    - stored composite scores labelled by analyst decisions
                 (confirmed fraud = 1, approved = 0, never alerted = 0)
"""
from datetime import timedelta
from decimal import Decimal

import numpy as np
from django.utils import timezone


def generate_synthetic_dataset(n_benign=200, n_fraud=50):
    """
    Generate a synthetic labeled dataset with clear benign / fraud patterns.
    Returns a list of dicts, each with the fields needed by the scoring pipeline.
    """
    rng = np.random.default_rng(42)
    records = []

    # Benign transactions: normal amounts, local, reasonable timing
    for i in range(n_benign):
        records.append({
            "amount": round(float(rng.uniform(10, 200)), 2),
            "hour": int(rng.integers(8, 22)),
            "day_of_week": int(rng.integers(0, 5)),
            "avg_spend": 100.0,
            "spend_stddev": 30.0,
            "lat": 40.7128 + float(rng.uniform(-0.05, 0.05)),
            "lng": -74.0060 + float(rng.uniform(-0.05, 0.05)),
            "last_lat": 40.7128,
            "last_lng": -74.0060,
            "elapsed_hours": float(rng.uniform(1, 48)),
            "is_fraud": 0,
        })

    # Fraud transactions: extreme amounts, impossible travel, or rapid velocity
    for i in range(n_fraud):
        fraud_type = rng.choice(["amount", "travel", "velocity"])
        rec = {
            "avg_spend": 100.0,
            "spend_stddev": 30.0,
            "last_lat": 40.7128,
            "last_lng": -74.0060,
            "is_fraud": 1,
        }
        if fraud_type == "amount":
            rec["amount"] = round(float(rng.uniform(800, 5000)), 2)
            rec["hour"] = int(rng.integers(0, 24))
            rec["day_of_week"] = int(rng.integers(0, 7))
            rec["lat"] = 40.7128 + float(rng.uniform(-0.05, 0.05))
            rec["lng"] = -74.0060 + float(rng.uniform(-0.05, 0.05))
            rec["elapsed_hours"] = float(rng.uniform(1, 48))
        elif fraud_type == "travel":
            rec["amount"] = round(float(rng.uniform(50, 300)), 2)
            rec["hour"] = int(rng.integers(0, 24))
            rec["day_of_week"] = int(rng.integers(0, 7))
            # Far away location
            rec["lat"] = float(rng.uniform(-30, 60))
            rec["lng"] = float(rng.uniform(-120, 120))
            rec["elapsed_hours"] = float(rng.uniform(0.01, 0.5))  # very short
        else:  # velocity
            rec["amount"] = round(float(rng.uniform(50, 200)), 2)
            rec["hour"] = int(rng.integers(0, 6))  # late night
            rec["day_of_week"] = int(rng.integers(5, 7))  # weekend
            rec["lat"] = 40.7128
            rec["lng"] = -74.0060
            rec["elapsed_hours"] = float(rng.uniform(0.001, 0.01))
        records.append(rec)

    rng.shuffle(records)
    return records


def load_csv_dataset(csv_path):
    """Load a labeled dataset from a CSV file."""
    import pandas as pd  # noqa: F811

    df = pd.read_csv(csv_path)
    required_cols = {"amount", "is_fraud"}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(
            f"CSV must contain at least columns: {required_cols}. "
            f"Found: {set(df.columns)}"
        )

    records = []
    for _, row in df.iterrows():
        records.append({
            "amount": float(row.get("amount", 100)),
            "hour": int(row.get("hour", 12)),
            "day_of_week": int(row.get("day_of_week", 0)),
            "avg_spend": float(row.get("avg_spend", 100)),
            "spend_stddev": float(row.get("spend_stddev", 30)),
            "lat": float(row.get("lat", 0)),
            "lng": float(row.get("lng", 0)),
            "last_lat": float(row.get("last_lat", 0)),
            "last_lng": float(row.get("last_lng", 0)),
            "elapsed_hours": float(row.get("elapsed_hours", 24)),
            "is_fraud": int(row.get("is_fraud", 0)),
        })
    return records


def score_record(record, model, threshold):
    """
    Score a single record through both the rule engine and ML model.
    Returns (predicted_fraud: bool, composite_score: float, factors: dict).
    """
    from risk.rules import (
        amount_anomaly_check,
        impossible_travel_check,
    )
    from risk.ml import extract_features, compute_ml_score

    # Build lightweight mock objects for the rule engine
    class MockAccount:
        id = 0
        avg_spend = Decimal(str(record["avg_spend"]))
        spend_stddev = Decimal(str(record["spend_stddev"]))
        last_known_lat = Decimal(str(record["last_lat"]))
        last_known_lng = Decimal(str(record["last_lng"]))
        last_transaction_at = timezone.now() - timedelta(
            hours=record.get("elapsed_hours", 24)
        )

    class MockTransaction:
        amount = Decimal(str(record["amount"]))
        currency = "USD"
        merchant = "Backtest"
        lat = Decimal(str(record["lat"]))
        lng = Decimal(str(record["lng"]))
        timestamp = timezone.now()
        idempotency_key = "backtest"

        class account:
            avg_spend = MockAccount.avg_spend
            spend_stddev = MockAccount.spend_stddev

    account = MockAccount()
    txn = MockTransaction()

    # Rule checks (skip velocity — requires stateful Redis sorted set)
    travel_trig, travel_det = impossible_travel_check(account, txn)
    amount_trig, amount_det = amount_anomaly_check(account, txn)

    rule_score = 0.0
    if travel_trig:
        rule_score += 0.40
    if amount_trig:
        rule_score += 0.30

    # ML score
    features = extract_features(txn, account=account)
    ml_raw = compute_ml_score(model, features)
    ml_contribution = ml_raw * 0.30

    composite = min(1.0, round(rule_score + ml_contribution, 4))

    return (
        composite >= threshold,
        composite,
        {
            "travel_triggered": travel_trig,
            "amount_triggered": amount_trig,
            "ml_score": round(ml_raw, 4),
        },
    )


def compute_metrics(y_true, y_pred):
    """Compute precision, recall, and F1 from label arrays."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round((tp + tn) / len(y_true), 4) if y_true else 0.0,
    }



THRESHOLDS = [round(t, 2) for t in np.arange(0.05, 1.0, 0.05)]


def _histogram(scores, labels, bins=20):
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        in_bin = (scores >= lo) & ((scores < hi) if i < bins - 1 else (scores <= hi))
        out.append({
            "start": round(float(lo), 2),
            "end": round(float(hi), 2),
            "fraud": int((in_bin & (labels == 1)).sum()),
            "legit": int((in_bin & (labels == 0)).sum()),
        })
    return out


def sweep(scores, labels, current_threshold):
    """Precision / recall / F1 for every threshold, plus a score histogram."""
    from sklearn.metrics import average_precision_score

    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    rows = []
    for t in sorted(set(THRESHOLDS + [round(float(current_threshold), 2)])):
        pred = (scores >= t).astype(int)
        rows.append({"threshold": t, **compute_metrics(labels.tolist(), pred.tolist())})
    best = max(rows, key=lambda r: (r["f1"], -abs(r["threshold"] - current_threshold)))
    current = next(r for r in rows if r["threshold"] == round(float(current_threshold), 2))
    both = len(set(labels.tolist())) == 2
    return {
        "samples": int(len(labels)),
        "fraud": int(labels.sum()),
        "legit": int((labels == 0).sum()),
        "average_precision": round(float(average_precision_score(labels, scores)), 4) if both else None,
        "current_threshold": float(current_threshold),
        "current": current,
        "best_f1": best,
        "thresholds": rows,
        "histogram": _histogram(scores, labels),
    }


def synthetic_backtest(current_threshold, n_benign=200, n_fraud=50):
    from risk.ml import load_model

    model = load_model()
    data = generate_synthetic_dataset(n_benign, n_fraud)
    scores, labels = [], []
    for rec in data:
        _, composite, _ = score_record(rec, model, current_threshold)
        scores.append(composite)
        labels.append(rec["is_fraud"])
    result = sweep(scores, labels, current_threshold)
    result["source"] = "synthetic"
    result["note"] = (
        f"{n_benign} benign and {n_fraud} fraudulent synthetic records replayed through the impossible-travel "
        "and amount rules plus the ML model (the stateful velocity rule is not replayed)."
    )
    return result


def analyst_backtest(current_threshold):
    from alerts.models import Alert
    from risk.models import RiskScore

    scores, labels, reviewed = [], [], 0
    qs = RiskScore.objects.select_related("transaction__alert").only("composite_score", "transaction__alert__status")
    for rs in qs.iterator(chunk_size=1000):
        alert = getattr(rs.transaction, "alert", None)
        if alert is not None and alert.status == Alert.Status.PENDING:
            continue
        if alert is not None:
            reviewed += 1
        scores.append(rs.composite_score)
        labels.append(1 if alert is not None and alert.status == Alert.Status.REJECTED else 0)
    if not labels:
        return {"source": "analyst", "samples": 0, "note": "No scored transactions yet."}
    result = sweep(scores, labels, current_threshold)
    result["source"] = "analyst"
    result["reviewed"] = reviewed
    result["note"] = (
        f"Stored composite scores labelled by analyst decisions ({reviewed} reviewed alerts). Transactions that never "
        "raised an alert count as legitimate, so recall above the live threshold is an upper bound."
    )
    return result
