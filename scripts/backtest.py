#!/usr/bin/env python
"""
Phase 8 — Backtesting Script.

Replays a labeled dataset through the full scoring pipeline (rules + ML)
and prints precision / recall / F1 against the known fraud labels.

Usage:
    # Generate a synthetic dataset and run the backtest:
    python scripts/backtest.py

    # Use a CSV file with known labels:
    python scripts/backtest.py --csv path/to/labeled_data.csv

    # Adjust the alert threshold:
    python scripts/backtest.py --threshold 0.5

Expected CSV columns (if providing a real dataset):
    amount, hour, day_of_week, avg_spend, spend_stddev, lat, lng,
    last_lat, last_lng, elapsed_hours, is_fraud (0 or 1)

If no CSV is provided, a synthetic dataset is generated with clear
fraud/benign patterns for demonstration.
"""
import argparse
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

# ─── Bootstrap Django ─────────────────────────────────────────────────────────
# Add the project root to sys.path so Django can find the settings module.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fraudguard.settings")

import django  # noqa: E402
django.setup()

import numpy as np  # noqa: E402
from django.utils import timezone  # noqa: E402
from datetime import timedelta  # noqa: E402


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


def main():
    parser = argparse.ArgumentParser(
        description="FraudGuard Backtesting — evaluate scoring pipeline against labeled data."
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to a labeled CSV dataset. If omitted, synthetic data is generated.",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.6,
        help="Composite score threshold for flagging as fraud (default: 0.6).",
    )
    parser.add_argument(
        "--n-benign", type=int, default=200,
        help="Number of synthetic benign transactions (default: 200).",
    )
    parser.add_argument(
        "--n-fraud", type=int, default=50,
        help="Number of synthetic fraud transactions (default: 50).",
    )
    args = parser.parse_args()

    # ─── Load dataset ─────────────────────────────────────────────────────
    print("=" * 70)
    print("  FraudGuard Backtesting Report")
    print("=" * 70)

    if args.csv:
        print(f"\n📂  Loading labeled dataset from: {args.csv}")
        dataset = load_csv_dataset(args.csv)
    else:
        print(f"\n🔧  Generating synthetic dataset: {args.n_benign} benign + {args.n_fraud} fraud")
        dataset = generate_synthetic_dataset(args.n_benign, args.n_fraud)

    total = len(dataset)
    n_positive = sum(1 for r in dataset if r["is_fraud"] == 1)
    n_negative = total - n_positive
    print(f"    Total records: {total} (fraud: {n_positive}, benign: {n_negative})")
    print(f"    Alert threshold: {args.threshold}")

    # ─── Load ML model ────────────────────────────────────────────────────
    from risk.ml import load_model
    model = load_model()
    model_status = "loaded" if model is not None else "disabled (not found)"
    print(f"    ML model: {model_status}")

    # ─── Score all records ────────────────────────────────────────────────
    print(f"\n⏳  Scoring {total} records...")
    start_time = time.time()

    y_true = []
    y_pred = []
    scores = []
    false_negatives = []
    false_positives = []

    for i, record in enumerate(dataset):
        predicted, composite, factors = score_record(record, model, args.threshold)
        y_true.append(record["is_fraud"])
        y_pred.append(1 if predicted else 0)
        scores.append(composite)

        if record["is_fraud"] == 1 and not predicted:
            false_negatives.append((i, record, composite, factors))
        if record["is_fraud"] == 0 and predicted:
            false_positives.append((i, record, composite, factors))

    elapsed = time.time() - start_time
    print(f"    Completed in {elapsed:.2f}s ({total/elapsed:.0f} records/sec)")

    # ─── Compute metrics ──────────────────────────────────────────────────
    metrics = compute_metrics(y_true, y_pred)

    print("\n" + "─" * 70)
    print("  RESULTS")
    print("─" * 70)
    print(f"\n  Confusion Matrix:")
    print(f"    ┌──────────────┬──────────────┐")
    print(f"    │ TP: {metrics['tp']:>7}  │ FP: {metrics['fp']:>7}  │")
    print(f"    ├──────────────┼──────────────┤")
    print(f"    │ FN: {metrics['fn']:>7}  │ TN: {metrics['tn']:>7}  │")
    print(f"    └──────────────┴──────────────┘")
    print(f"\n  Precision:  {metrics['precision']:.4f}")
    print(f"  Recall:     {metrics['recall']:.4f}")
    print(f"  F1 Score:   {metrics['f1']:.4f}")
    print(f"  Accuracy:   {metrics['accuracy']:.4f}")

    # ─── Score distribution ───────────────────────────────────────────────
    fraud_scores = [s for s, t in zip(scores, y_true) if t == 1]
    benign_scores = [s for s, t in zip(scores, y_true) if t == 0]

    print(f"\n  Score Distribution:")
    print(f"    Fraud    — mean: {np.mean(fraud_scores):.4f}, "
          f"min: {np.min(fraud_scores):.4f}, max: {np.max(fraud_scores):.4f}")
    print(f"    Benign   — mean: {np.mean(benign_scores):.4f}, "
          f"min: {np.min(benign_scores):.4f}, max: {np.max(benign_scores):.4f}")

    # ─── Sample errors ────────────────────────────────────────────────────
    if false_negatives:
        print(f"\n  ⚠️  False Negatives (missed fraud): {len(false_negatives)}")
        for idx, rec, score, factors in false_negatives[:5]:
            print(f"    #{idx}: amount=${rec['amount']:.2f}, score={score:.4f}, {factors}")

    if false_positives:
        print(f"\n  ⚠️  False Positives (false alarms): {len(false_positives)}")
        for idx, rec, score, factors in false_positives[:5]:
            print(f"    #{idx}: amount=${rec['amount']:.2f}, score={score:.4f}, {factors}")

    print("\n" + "=" * 70)
    print("  Backtest complete.")
    print("=" * 70)

    return metrics


if __name__ == "__main__":
    main()
