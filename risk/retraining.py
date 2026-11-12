"""
Retrain the ML anomaly model from analyst decisions (champion / challenger).

Labels come from the review workflow:
  * alert confirmed as fraud (status "rejected")  -> 1
  * alert approved as legitimate (status "approved") -> 0
  * scored transaction that never raised an alert -> 0 (presumed legitimate)
Pending alerts are left out because nobody has judged them yet.

The labelled rows are split into a training part and a stratified holdout.
A challenger Isolation Forest is fitted on the legitimate rows of the training
part only (an unsupervised model must learn what *normal* looks like), then
the challenger and the current production model (champion) are both scored on
the holdout. The challenger is promoted only if its average precision is at
least as good as the champion's. A promoted model is refitted on every
legitimate row and stored in the database (ModelVersion.artifact), so it
survives restarts on hosts with ephemeral disks. It is hot-swapped into the
running process, and other processes load it on their next model check. The
model file at ML_MODEL_PATH stays the shipped baseline.
"""
import io
import logging

import joblib
import numpy as np
from django.conf import settings
from django.utils import timezone
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from risk.ml import FEATURE_NAMES, extract_features, ml_scores_batch

logger = logging.getLogger(__name__)

# Score above which the ML component alone calls a transaction anomalous,
# used only for the precision/recall figures in the report.
ML_FLAG_AT = 0.5


def _setting(name, default):
    return getattr(settings, name, default)


def build_dataset():
    """
    Returns (X, y, human) for every scored transaction with a usable label.
    `human` marks rows whose label came from an analyst decision.
    """
    from alerts.models import Alert
    from risk.models import RiskScore

    X, y, human = [], [], []
    qs = RiskScore.objects.select_related("transaction", "transaction__account", "transaction__alert")
    for rs in qs.iterator(chunk_size=500):
        txn = rs.transaction
        alert = getattr(txn, "alert", None)
        if alert is None:
            label, by_human = 0, False
        elif alert.status == Alert.Status.REJECTED:
            label, by_human = 1, True
        elif alert.status == Alert.Status.APPROVED:
            label, by_human = 0, True
        else:
            continue  # pending: no verdict yet

        feats = (rs.factors or {}).get("ml_features")
        if not feats or len(feats) != len(FEATURE_NAMES):
            # Older scores predate feature capture: rebuild from the current
            # account profile (an approximation of the profile at scoring time).
            feats = extract_features(txn, account=txn.account)[0].tolist()
        X.append([float(v) for v in feats])
        y.append(label)
        human.append(by_human)
    return np.array(X, dtype=float).reshape(-1, len(FEATURE_NAMES)), np.array(y, dtype=int), np.array(human, dtype=bool)


def _evaluate(model, X, y):
    if model is None:
        return None
    scores = ml_scores_batch(model, X)
    flagged = (scores >= ML_FLAG_AT).astype(int)
    out = {
        "average_precision": round(float(average_precision_score(y, scores)), 4),
        "precision": round(float(precision_score(y, flagged, zero_division=0)), 4),
        "recall": round(float(recall_score(y, flagged, zero_division=0)), 4),
    }
    out["roc_auc"] = round(float(roc_auc_score(y, scores)), 4) if len(set(y.tolist())) == 2 else None
    return out


def _fit(X_legit, contamination, random_state):
    model = IsolationForest(
        n_estimators=_setting("RETRAIN_N_ESTIMATORS", 100),
        contamination=contamination,
        random_state=random_state,
        n_jobs=1,
    )
    model.fit(X_legit)
    return model


def retrain(trigger="manual", force=False, user=None, dry_run=False, random_state=42):
    """
    Run one champion/challenger retraining cycle. Returns a result dict.
    `force` promotes the challenger even if it does not beat the champion
    (the minimum-label checks still apply).
    """
    from audit.models import AuditLog
    from risk.models import ModelVersion
    import risk.tasks as tasks

    min_fraud = _setting("RETRAIN_MIN_FRAUD_LABELS", 5)
    min_samples = _setting("RETRAIN_MIN_SAMPLES", 50)

    X, y, human = build_dataset()
    n_fraud = int(y.sum())
    n_legit_reviewed = int(((y == 0) & human).sum())
    summary = {
        "samples": int(len(y)),
        "labeled_fraud": n_fraud,
        "labeled_legit": n_legit_reviewed,
        "presumed_legit": int(((y == 0) & ~human).sum()),
    }
    if len(y) < min_samples or n_fraud < min_fraud:
        reason = (
            f"Need at least {min_samples} scored transactions and {min_fraud} confirmed-fraud labels; "
            f"have {len(y)} and {n_fraud}."
        )
        logger.info("retrain skipped: %s", reason)
        return {"status": "skipped", "reason": reason, **summary}

    contamination = float(np.clip(n_fraud / len(y), 0.005, 0.1))
    X_tr, X_ho, y_tr, y_ho = train_test_split(X, y, test_size=0.3, stratify=y, random_state=random_state)

    challenger = _fit(X_tr[y_tr == 0], contamination, random_state)
    tasks.refresh_model(force=True)
    champion = tasks.ML_MODEL
    champion_version = tasks.ML_MODEL_VERSION if champion is not None else None

    challenger_m = _evaluate(challenger, X_ho, y_ho)
    champion_m = _evaluate(champion, X_ho, y_ho)
    beats = champion_m is None or challenger_m["average_precision"] >= champion_m["average_precision"]
    promote = (beats or force) and not dry_run

    version = base = "iforest-" + timezone.now().strftime("%Y%m%d-%H%M%S")
    n = 1
    while ModelVersion.objects.filter(version=version).exists():
        n += 1
        version = f"{base}-{n}"
    metrics = {
        "holdout_size": int(len(y_ho)),
        "holdout_fraud": int(y_ho.sum()),
        "challenger": challenger_m,
        "champion": champion_m,
        "champion_version": champion_version,
        "challenger_beats_champion": bool(beats),
        "ml_flag_at": ML_FLAG_AT,
    }
    if dry_run:
        notes = "Dry run: nothing saved."
    elif promote and not beats:
        notes = "Promoted with force although it did not beat the champion."
    elif promote:
        notes = "Challenger matched or beat the champion on the holdout and was promoted."
    else:
        notes = "Challenger did not beat the champion; production model unchanged."

    result = {
        "status": "promoted" if promote else ("dry_run" if dry_run else "kept_champion"),
        "version": version,
        "contamination": round(contamination, 4),
        "metrics": metrics,
        "notes": notes,
        **summary,
    }
    if dry_run:
        return result

    artifact = None
    if promote:
        final = _fit(X[y == 0], contamination, random_state)
        buf = io.BytesIO()
        joblib.dump({
            "model": final,
            "feature_names": FEATURE_NAMES,
            "model_version": version,
            "trained_at": timezone.now().isoformat(),
            "contamination": contamination,
            "train_samples": int((y == 0).sum()),
            "metrics": metrics,
        }, buf, compress=3)
        artifact = buf.getvalue()
        tasks.install_model(final, version)

    ModelVersion.objects.create(
        version=version,
        trigger=trigger,
        promoted=promote,
        train_samples=int((y == 0).sum()),
        labeled_fraud=n_fraud,
        labeled_legit=n_legit_reviewed,
        contamination=contamination,
        metrics=metrics,
        notes=notes,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        artifact=artifact,
    )
    AuditLog.objects.create(
        actor=user if getattr(user, "is_authenticated", False) else None,
        action="model_promoted" if promote else "model_retrained",
        target=f"Model:{version}",
        payload={"trigger": trigger, "notes": notes, **summary, "metrics": metrics},
    )
    logger.info("retrain %s: %s", version, notes)
    return result
