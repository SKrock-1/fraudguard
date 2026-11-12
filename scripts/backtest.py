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


from risk.backtest import compute_metrics, generate_synthetic_dataset, load_csv_dataset, score_record  # noqa: E402


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
