"""
ML scoring module for FraudGuard.

Loads the offline-trained Isolation Forest model once at process start
(module-level) and provides feature extraction and anomaly scoring.
"""
import logging
from pathlib import Path
from typing import Optional, Any
import numpy as np
import joblib
from django.conf import settings

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "amount",
    "hour",
    "day_of_week",
    "amount_to_avg",
    "z_score",
]


def extract_features(transaction, account=None) -> np.ndarray:
    """
    Extract the standard 5-feature vector from a Transaction and its Account.
    Returns a 2D numpy array of shape (1, 5).
    """
    if account is None:
        account = getattr(transaction, "account", None)

    amount = float(transaction.amount)

    ts = getattr(transaction, "timestamp", None)
    if ts is not None and hasattr(ts, "hour"):
        hour = float(ts.hour)
        day_of_week = float(ts.weekday())
    else:
        hour = 12.0
        day_of_week = 0.0

    avg_spend = float(account.avg_spend) if (account and account.avg_spend) else 0.0
    spend_stddev = float(account.spend_stddev) if (account and account.spend_stddev) else 0.0

    # Ratio to rolling avg spend
    amount_to_avg = (amount / (avg_spend + 1.0)) if avg_spend > 0 else 1.0

    # Z-score against account spend history
    if spend_stddev > 0 and avg_spend > 0:
        z_score = (amount - avg_spend) / spend_stddev
    else:
        z_score = 0.0

    return np.array([[amount, hour, day_of_week, amount_to_avg, z_score]], dtype=float)


def load_bundle(model_path: Optional[str] = None) -> Optional[dict]:
    """Load the full model bundle (model + metadata), or None if unavailable."""
    if model_path is None:
        model_path = getattr(settings, "ML_MODEL_PATH", None)
    if not model_path or not Path(model_path).exists():
        return None
    try:
        bundle = joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load ML model bundle from %s: %s", model_path, e)
        return None
    if isinstance(bundle, dict) and "model" in bundle:
        return bundle
    return {"model": bundle, "model_version": "unknown"}


def isolation_score_from_decision(raw: np.ndarray) -> np.ndarray:
    """
    Map IsolationForest decision_function values to a 0..1 anomaly score.
    raw >= 0.05 is a clear inlier (0.0); raw <= -0.15 a strong outlier (1.0).
    """
    return np.clip((0.05 - np.asarray(raw, dtype=float)) / 0.20, 0.0, 1.0)


def ml_scores_batch(model: Any, X: np.ndarray) -> np.ndarray:
    """Vectorised compute_ml_score for a feature matrix of shape (n, 5)."""
    X = np.asarray(X, dtype=float)
    if model is None or len(X) == 0:
        return np.zeros(len(X))
    if hasattr(model, "decision_function") and not hasattr(model, "predict_risk") and not hasattr(model, "predict_proba"):
        return isolation_score_from_decision(model.decision_function(X))
    return np.array([compute_ml_score(model, row.reshape(1, -1)) for row in X])


def load_model(model_path: Optional[str] = None) -> Any:
    """
    Load the serialized model bundle from disk via joblib.
    Unwraps the bundle dictionary if present, returning the fitted estimator.
    """
    if model_path is None:
        model_path = getattr(settings, "ML_MODEL_PATH", None)

    if not model_path:
        logger.warning("ML_MODEL_PATH not configured; ML scorer disabled.")
        return None

    path = Path(model_path)
    if not path.exists():
        logger.warning("ML model file %s does not exist; ML scorer disabled.", path)
        return None

    try:
        bundle = joblib.load(path)
        if isinstance(bundle, dict) and "model" in bundle:
            logger.info("Loaded ML model bundle %s (trained: %s)", path, bundle.get("trained_at"))
            return bundle["model"]
        return bundle
    except Exception as e:
        logger.error("Failed to load ML model from %s: %s", path, e)
        return None


def compute_ml_score(model: Any, features: np.ndarray) -> float:
    """
    Compute a continuous anomaly score in [0.0, 1.0] from a fitted model or mock.

    Mapping:
    - 0.0 = completely benign / normal transaction
    - 1.0 = extreme anomaly / high outlier
    """
    if model is None:
        return 0.0

    # Support custom / mocked models with direct predict_risk or score attribute
    if hasattr(model, "predict_risk") and callable(model.predict_risk):
        score = float(model.predict_risk(features))
        return float(np.clip(score, 0.0, 1.0))

    if hasattr(model, "predict_proba") and callable(model.predict_proba):
        proba = model.predict_proba(features)
        return float(np.clip(proba[0][1], 0.0, 1.0))

    # scikit-learn IsolationForest decision_function
    if hasattr(model, "decision_function") and callable(model.decision_function):
        raw = float(model.decision_function(features)[0])
        return float(isolation_score_from_decision(raw))

    # Direct callable (e.g. MagicMock return_value or custom function)
    if callable(model):
        res = model(features)
        if isinstance(res, (int, float, np.number)):
            return float(np.clip(res, 0.0, 1.0))

    return 0.0


def ml_score(transaction, account=None, model: Any = None) -> float:
    """
    Calculate the ML anomaly risk score for a transaction.
    Returns float in [0.0, 1.0].
    """
    active_model = model if model is not None else ML_MODEL
    if active_model is None:
        return 0.0

    features = extract_features(transaction, account=account)
    return round(compute_ml_score(active_model, features), 4)


# Loaded once at process start (module-level) as required by PRD
ML_MODEL = load_model()
