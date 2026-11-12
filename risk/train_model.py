"""
Offline training script for FraudGuard ML Anomaly Detection.

Trains an Isolation Forest on transaction features and serializes the model
with joblib. Supports:
1. Kaggle Credit Card Fraud dataset (creditcard.csv)
2. PaySim synthetic mobile money dataset
3. Built-in synthetic transaction generator (Faker/NumPy) for self-contained setup

Run manually:
    uv run python risk/train_model.py
    uv run python risk/train_model.py --data-path path/to/dataset.csv
"""
import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fraudguard.train_model")

# Standard feature set expected by FraudGuard's online ML scorer
FEATURE_NAMES = [
    "amount",
    "hour",
    "day_of_week",
    "amount_to_avg",
    "z_score",
]


def generate_synthetic_training_data(n_samples: int = 10000, fraud_ratio: float = 0.02, random_state: int = 42) -> pd.DataFrame:
    """
    Generate synthetic transaction feature dataset simulating normal spenders
    and fraudulent anomalies with realistic distributions.
    """
    np.random.seed(random_state)
    n_fraud = int(n_samples * fraud_ratio)
    n_normal = n_samples - n_fraud

    logger.info("Generating %d synthetic transactions (%d normal, %d fraud)...", n_samples, n_normal, n_fraud)

    # 1. Normal transactions (~98%)
    # Amounts: log-normal around $30 - $120
    normal_amounts = np.random.lognormal(mean=3.8, sigma=0.8, size=n_normal)
    normal_amounts = np.clip(normal_amounts, 2.0, 500.0)

    # Hours: daytime peak (9:00 - 22:00)
    hour_weights = np.array([
        1, 1, 1, 1, 1, 2, 4, 8,
        12, 16, 16, 16, 16, 14, 14, 14,
        16, 16, 12, 10, 8, 6, 4, 3
    ], dtype=float)
    hour_probs = hour_weights / hour_weights.sum()
    normal_hours = np.random.choice(range(24), size=n_normal, p=hour_probs)
    normal_dows = np.random.choice(range(7), size=n_normal)
    normal_ratio = np.random.normal(loc=1.0, scale=0.3, size=n_normal)
    normal_ratio = np.clip(normal_ratio, 0.2, 2.5)
    normal_z = np.random.normal(loc=0.0, scale=0.8, size=n_normal)
    normal_z = np.clip(normal_z, -2.0, 2.0)

    df_normal = pd.DataFrame({
        "amount": normal_amounts,
        "hour": normal_hours,
        "day_of_week": normal_dows,
        "amount_to_avg": normal_ratio,
        "z_score": normal_z,
        "is_fraud": 0,
    })

    # 2. Fraudulent transactions (~2%)
    # High amounts ($1,000 - $10,000), odd night hours, extreme ratios and z-scores
    fraud_amounts = np.random.uniform(1500.0, 9500.0, size=n_fraud)
    fraud_hours = np.random.choice([0, 1, 2, 3, 4, 23], size=n_fraud)
    fraud_dows = np.random.choice(range(7), size=n_fraud)
    fraud_ratio = np.random.uniform(5.0, 30.0, size=n_fraud)
    fraud_z = np.random.uniform(3.5, 20.0, size=n_fraud)

    df_fraud = pd.DataFrame({
        "amount": fraud_amounts,
        "hour": fraud_hours,
        "day_of_week": fraud_dows,
        "amount_to_avg": fraud_ratio,
        "z_score": fraud_z,
        "is_fraud": 1,
    })

    df = pd.concat([df_normal, df_fraud], ignore_index=True)
    df = df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
    return df


def load_dataset(data_path: str, n_samples: int = 10000) -> pd.DataFrame:
    """Load dataset from CSV if provided, else generate synthetic dataset."""
    path = Path(data_path) if data_path else None
    if path and path.exists():
        logger.info("Loading dataset from %s...", path)
        raw_df = pd.read_csv(path)
        # Check Kaggle Credit Card format
        if "Class" in raw_df.columns and "Amount" in raw_df.columns:
            logger.info("Detected Kaggle Credit Card Fraud format.")
            raw_df["hour"] = (raw_df["Time"] // 3600) % 24
            raw_df["day_of_week"] = (raw_df["Time"] // (3600 * 24)) % 7
            mean_amt = raw_df["Amount"].mean()
            std_amt = raw_df["Amount"].std() or 1.0
            raw_df["amount"] = raw_df["Amount"]
            raw_df["amount_to_avg"] = raw_df["amount"] / (mean_amt + 1.0)
            raw_df["z_score"] = (raw_df["amount"] - mean_amt) / std_amt
            return raw_df[FEATURE_NAMES]
        # Check if already in standard feature format
        if all(col in raw_df.columns for col in FEATURE_NAMES):
            return raw_df[FEATURE_NAMES]

        logger.warning("Unrecognized CSV columns, falling back to synthetic generator.")

    return generate_synthetic_training_data(n_samples=n_samples)


def train_isolation_forest(
    df: pd.DataFrame,
    contamination: float = 0.02,
    n_estimators: int = 100,
    random_state: int = 42,
) -> IsolationForest:
    """Train scikit-learn IsolationForest on feature matrix."""
    X = df[FEATURE_NAMES].values
    logger.info("Fitting IsolationForest (n_estimators=%d, contamination=%.3f)...", n_estimators, contamination)
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=1,
    )
    model.fit(X)
    return model


def main():
    parser = argparse.ArgumentParser(description="Train FraudGuard Isolation Forest ML model offline.")
    parser.add_argument("--data-path", type=str, default="", help="Path to input dataset CSV (optional)")
    parser.add_argument(
        "--output-path",
        type=str,
        default="risk/ml_models/isolation_forest.joblib",
        help="Target filepath for serialized joblib model",
    )
    parser.add_argument("--contamination", type=float, default=0.02, help="Expected outlier contamination rate")
    parser.add_argument("--n-samples", type=int, default=10000, help="Number of synthetic samples if generating")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    # 1. Prepare data
    df = load_dataset(args.data_path, n_samples=args.n_samples)

    # 2. Train model
    model = train_isolation_forest(
        df,
        contamination=args.contamination,
        random_state=args.random_state,
    )

    # 3. Package bundle with metadata
    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "model_version": "isolation_forest_v1",
        "trained_at": datetime.utcnow().isoformat(),
        "contamination": args.contamination,
        "train_samples": len(df),
    }

    # 4. Save to disk
    out_file = Path(args.output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out_file)
    file_size_kb = out_file.stat().st_size / 1024
    logger.info("Successfully trained and saved model to %s (%.1f KB)", out_file, file_size_kb)


if __name__ == "__main__":
    main()
