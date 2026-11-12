#!/usr/bin/env python
"""
Benchmark FraudGuard's ML component on a real, public fraud dataset.

Dataset: ULB "Credit Card Fraud Detection" (Dal Pozzolo et al., 2015) -
284,807 real European card transactions from two days in September 2013,
492 of them fraudulent. Fetched from OpenML (data id 1597, no account needed)
and cached under data/ (git-ignored).

The dataset has no account ids, merchants or locations, so the rule engine
(velocity, impossible travel, per-account z-score) cannot be replayed on it.
The benchmark therefore evaluates the unsupervised Isolation Forest, the part
of the pipeline that does not depend on account history, in two settings:

  A. "FraudGuard features": the live scorer's amount-based features (amount,
     amount-to-average, amount z-score), with the averages taken over the
     whole population instead of per account. OpenML's copy of the dataset
     omits the Time column, so the hour and day-of-week features (2 of the 5)
     cannot be derived and are left out.
  B. "Full features": the dataset's 28 PCA components plus the amount, to
     show what the same algorithm reaches with richer signals.

Protocol: stratified 70/30 split; the model is fitted on legitimate training
rows only (as in production retraining) and scored on the untouched test
split. Reported: average precision (PR-AUC), ROC-AUC, and precision/recall
when analysts can review a fixed share of traffic (alert budget).

Usage:
    python scripts/benchmark_public_dataset.py            # writes benchmarks/
    python scripts/benchmark_public_dataset.py --quick    # 25 % sample
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fraudguard.settings")

import django  # noqa: E402

django.setup()

DATA_HOME = ROOT / "data" / "openml"
OUT_DIR = ROOT / "benchmarks"
OPENML_ID = 1597
BUDGETS = [0.001, 0.0025, 0.005, 0.01]  # share of traffic sent to analysts
SEED = 42


def load(quick: bool):
    from sklearn.datasets import fetch_openml

    print(f"Loading OpenML dataset {OPENML_ID} (cached in {DATA_HOME}) ...")
    ds = fetch_openml(data_id=OPENML_ID, data_home=str(DATA_HOME), as_frame=True, parser="auto")
    df = ds.frame.copy()
    target = ds.target_names[0] if ds.target_names else "Class"
    y = df[target].astype(str).str.strip("'").astype(int).to_numpy()
    df = df.drop(columns=[target])
    if quick:
        idx = train_test_split(np.arange(len(y)), train_size=0.25, stratify=y, random_state=SEED)[0]
        df, y = df.iloc[idx].reset_index(drop=True), y[idx]
    return df, y


def fraudguard_features(df, stats):
    """The live scorer's amount features, with population statistics as the 'account' baseline."""
    amount = df["Amount"].to_numpy(dtype=float)
    amount_to_avg = amount / (stats["mean"] + 1.0)
    z = (amount - stats["mean"]) / stats["std"]
    features = [amount, amount_to_avg, z]
    if "Time" in df.columns:  # present in the Kaggle CSV, absent from OpenML
        t = df["Time"].to_numpy(dtype=float)
        features += [(t // 3600) % 24, (t // 86400) % 7]
    return np.column_stack(features)


def full_features(df):
    cols = [c for c in df.columns if c.startswith("V")]
    return np.column_stack([df[cols].to_numpy(dtype=float), np.log1p(df["Amount"].to_numpy(dtype=float))])


def evaluate(name, X_tr, y_tr, X_te, y_te, contamination):
    from risk.ml import isolation_score_from_decision

    t0 = time.time()
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=SEED, n_jobs=-1)
    model.fit(X_tr[y_tr == 0])
    fit_s = time.time() - t0
    raw = -model.score_samples(X_te)  # higher = more anomalous
    fg_score = isolation_score_from_decision(model.decision_function(X_te))

    order = np.argsort(-raw)
    budgets = []
    for b in BUDGETS:
        k = max(1, int(round(b * len(y_te))))
        tp = int(y_te[order[:k]].sum())
        budgets.append({
            "review_share": b,
            "alerts": k,
            "caught": tp,
            "precision": round(tp / k, 4),
            "recall": round(tp / int(y_te.sum()), 4),
        })
    flagged = fg_score >= 0.5
    tp = int((flagged & (y_te == 1)).sum())
    result = {
        "name": name,
        "features": int(X_tr.shape[1]),
        "average_precision": round(float(average_precision_score(y_te, raw)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, raw)), 4),
        "fit_seconds": round(fit_s, 2),
        "alert_budgets": budgets,
        "fraudguard_mapping": {
            "flagged": int(flagged.sum()),
            "precision": round(tp / max(1, int(flagged.sum())), 4),
            "recall": round(tp / int(y_te.sum()), 4),
            "note": "ML score >= 0.5 on FraudGuard's 0..1 anomaly scale",
        },
    }
    print(f"  {name:<22} AP {result['average_precision']:.3f}  ROC-AUC {result['roc_auc']:.3f}  ({fit_s:.1f}s)")
    return result


def write_markdown(res, path):
    lines = [
        "# Benchmark: ULB credit-card fraud (real data)",
        "",
        f"Generated {res['generated_at']} by `scripts/benchmark_public_dataset.py`.",
        "",
        f"- Dataset: {res['dataset']['name']} - {res['dataset']['rows']:,} transactions, "
        f"{res['dataset']['fraud']:,} fraud ({res['dataset']['fraud_rate'] * 100:.3f} %).",
        f"- Test split: {res['split']['test_rows']:,} transactions, {res['split']['test_fraud']} fraud. "
        "The model is fitted on legitimate training rows only.",
        f"- A random detector would score average precision {res['dataset']['fraud_rate']:.4f}.",
        "- *FraudGuard features* are the live scorer's amount features (amount, amount-to-average, amount z-score). "
        "OpenML's copy omits the `Time` column, so the hour and day-of-week features are unavailable. The rules "
        "(velocity, impossible travel, per-account z-score) need account ids and locations, which this dataset lacks.",
        "",
        "| Setting | Features | Average precision | ROC-AUC |",
        "|---|---|---|---|",
    ]
    for r in res["results"]:
        lines.append(f"| {r['name']} | {r['features']} | {r['average_precision']:.3f} | {r['roc_auc']:.3f} |")
    lines += ["", "## Analyst alert budget", "",
              "If analysts can review a fixed share of traffic, the highest-scoring transactions are sent first:", "",
              "| Setting | Review share | Alerts | Fraud caught | Precision | Recall |", "|---|---|---|---|---|---|"]
    for r in res["results"]:
        for b in r["alert_budgets"]:
            lines.append(f"| {r['name']} | {b['review_share'] * 100:.2f} % | {b['alerts']:,} | {b['caught']} | "
                         f"{b['precision']:.2f} | {b['recall']:.2f} |")
    lines += ["", "## Reading the results", "", res["interpretation"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--quick", action="store_true", help="Use a 25 %% stratified sample")
    args = ap.parse_args()

    df, y = load(args.quick)
    print(f"  {len(y):,} rows, {int(y.sum())} fraud ({y.mean() * 100:.3f} %)")
    idx_tr, idx_te = train_test_split(np.arange(len(y)), test_size=0.3, stratify=y, random_state=SEED)
    df_tr, df_te, y_tr, y_te = df.iloc[idx_tr], df.iloc[idx_te], y[idx_tr], y[idx_te]

    legit_amount = df_tr["Amount"].to_numpy(dtype=float)[y_tr == 0]
    stats = {"mean": float(legit_amount.mean()), "std": float(legit_amount.std() or 1.0)}
    contamination = float(np.clip(y_tr.mean(), 0.0005, 0.5))

    print("Fitting Isolation Forest ...")
    results = [
        evaluate("FraudGuard features", fraudguard_features(df_tr, stats), y_tr, fraudguard_features(df_te, stats), y_te, contamination),
        evaluate("Full features (V1-V28)", full_features(df_tr), y_tr, full_features(df_te), y_te, contamination),
    ]
    a, b = results
    rate = float(y.mean())
    if a["roc_auc"] < 0.6:
        first = (
            f"Amount on its own carries almost no signal in this dataset: with FraudGuard's amount-based features and "
            f"a population-wide baseline the model scores ROC-AUC {a['roc_auc']:.2f} (0.5 is chance) and average "
            f"precision {a['average_precision']:.3f}, against {rate:.4f} for a random detector. Fraudulent and "
            "legitimate amounts overlap heavily, so a single baseline for everyone cannot separate them."
        )
    else:
        first = (
            f"With FraudGuard's amount-based features and a population-wide baseline the model scores ROC-AUC "
            f"{a['roc_auc']:.2f} and average precision {a['average_precision']:.3f}, against {rate:.4f} for a random detector."
        )
    interpretation = (
        first
        + f" On the dataset's 28 behavioural features the same algorithm reaches ROC-AUC {b['roc_auc']:.2f} and "
        f"average precision {b['average_precision']:.3f}. Two conclusions follow. First, per-account baselines matter: "
        "FraudGuard compares each amount with that account's own spending history, which this anonymised dataset "
        "cannot provide. Second, the ML score is rightly a supporting signal (weight 0.30) next to explainable rules "
        "that use account history and location; richer features (device, merchant category, behaviour) would improve "
        "detection more than a different model would."
    )
    res = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "quick_sample": args.quick,
        "dataset": {
            "name": "ULB Credit Card Fraud Detection (OpenML 1597)",
            "rows": int(len(y)),
            "fraud": int(y.sum()),
            "fraud_rate": round(float(y.mean()), 6),
            "source": "https://www.openml.org/d/1597",
        },
        "split": {"test_rows": int(len(y_te)), "test_fraud": int(y_te.sum()), "seed": SEED},
        "model": {"algorithm": "IsolationForest", "n_estimators": 200, "contamination": round(contamination, 6)},
        "results": results,
        "interpretation": interpretation,
    }
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "ulb_creditcard.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    write_markdown(res, OUT_DIR / "README.md")
    print(f"\nWrote {OUT_DIR / 'ulb_creditcard.json'} and {OUT_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
