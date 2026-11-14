import logging
from celery import shared_task
from django.db import transaction as db_transaction
import os
import time

from risk.ml import extract_features, load_bundle, ml_score

logger = logging.getLogger(__name__)

# Loaded once per process on first use (ensure_model), not at import: the web
# process imports this module to enqueue tasks, and only the worker needs the
# model. Retrained models are stored in the database; refresh_model() picks up
# a newer promoted one (or a replaced baseline file) at most every 30 seconds.
_UNLOADED = object()
ML_MODEL = _UNLOADED
ML_MODEL_VERSION = "isolation_forest_v1"
_MODEL_FILE_STATE = {"key": None, "checked_at": 0.0}


def ensure_model():
    """Load the baseline model the first time it is needed in this process."""
    global ML_MODEL, ML_MODEL_VERSION
    if ML_MODEL is _UNLOADED:
        bundle = load_bundle()
        ML_MODEL = bundle["model"] if bundle else None
        ML_MODEL_VERSION = (bundle or {}).get("model_version", "isolation_forest_v1")
        _MODEL_FILE_STATE["key"] = _model_file_key()
    return ML_MODEL
MODEL_RECHECK_SECONDS = 30.0


def _model_file_key():
    from django.conf import settings
    path = getattr(settings, "ML_MODEL_PATH", None)
    try:
        return (path, os.stat(path).st_mtime_ns) if path else None
    except OSError:
        return (path, None)


def install_model(model, version):
    """Swap the in-process model (used after a retrain is promoted)."""
    global ML_MODEL, ML_MODEL_VERSION
    ML_MODEL = model
    ML_MODEL_VERSION = version
    _MODEL_FILE_STATE["key"] = _model_file_key()
    _MODEL_FILE_STATE["checked_at"] = time.monotonic()


def _latest_promoted():
    """(version, artifact bytes) of the newest promoted model stored in the DB."""
    from django.db import DatabaseError
    from risk.models import ModelVersion
    try:
        row = (
            ModelVersion.objects.filter(promoted=True, artifact__isnull=False)
            .order_by("-trained_at", "-id")
            .values_list("version", flat=True)
            .first()
        )
        if not row or row == ML_MODEL_VERSION:
            return row, None
        art = ModelVersion.objects.filter(version=row).values_list("artifact", flat=True).first()
        return row, bytes(art) if art else None
    except DatabaseError:
        return None, None


def refresh_model(force=False):
    """
    Keep the in-process model current, checking at most every 30 seconds:
    1. a newer promoted model in the database (from retraining) wins;
    2. otherwise reload the baseline file if it changed on disk.
    """
    ensure_model()
    now = time.monotonic()
    if not force and now - _MODEL_FILE_STATE["checked_at"] < MODEL_RECHECK_SECONDS:
        return
    _MODEL_FILE_STATE["checked_at"] = now

    version, artifact = _latest_promoted()
    if artifact:
        import io
        import joblib
        try:
            bundle = joblib.load(io.BytesIO(artifact))
            install_model(bundle["model"], bundle.get("model_version", version))
            logger.info("Loaded promoted ML model %s from the database", version)
        except Exception as e:  # a corrupt artifact must not stop scoring
            logger.error("Could not load promoted model %s: %s", version, e)
        return
    if version:
        return  # already running the newest promoted model

    key = _model_file_key()
    if _MODEL_FILE_STATE["key"] is None:
        _MODEL_FILE_STATE["key"] = key
        return
    if key != _MODEL_FILE_STATE["key"]:
        bundle = load_bundle()
        if bundle:
            install_model(bundle["model"], bundle.get("model_version", "unknown"))
            logger.info("Reloaded ML model %s from disk", ML_MODEL_VERSION)
        else:
            _MODEL_FILE_STATE["key"] = key


RULE_WEIGHTS = {
    "velocity": 0.30,
    "impossible_travel": 0.40,
    "amount_anomaly": 0.30,
}
ML_WEIGHT = 0.30


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def score_transaction(self, transaction_id: int) -> dict:
    """
    Celery task: score a transaction through the rule engine and ML model,
    combining them into an explainable composite RiskScore.

    Pipeline:
        1. Load Transaction + Account from DB
        2. Run all deterministic rules via evaluate_rules()
        3. Run ML anomaly scoring via ml_score() using module-level loaded model
        4. Combine rule engine and ML output into a composite risk score [0.0, 1.0]
        5. Persist RiskScore with full explainability breakdown in factors JSONField
        6. Mark Transaction as 'scored'

    Retry policy: up to 3 retries with exponential backoff on transient
    connection errors (Redis, DB).
    """
    from transactions.models import Transaction
    from risk.models import RiskScore
    from risk.rules import evaluate_rules

    try:
        txn = Transaction.objects.select_related("account").get(id=transaction_id)
    except Transaction.DoesNotExist:
        logger.error("score_transaction: Transaction %s not found, skipping.", transaction_id)
        return {"status": "error", "reason": "transaction_not_found"}

    # Skip if already scored (idempotent)
    if txn.status == Transaction.Status.SCORED:
        logger.info("score_transaction: Transaction %s already scored, skipping.", transaction_id)
        return {"status": "skipped", "reason": "already_scored"}

    account = txn.account

    # Step 1: Run deterministic rule engine
    rule_results = evaluate_rules(account, txn)

    # Step 2: Run ML anomaly scorer (features are kept for later retraining)
    refresh_model()
    ml_features = [round(float(v), 6) for v in extract_features(txn, account=account)[0]]
    ml_score_val = ml_score(txn, account=account, model=ML_MODEL)
    ml_contribution = round(ml_score_val * ML_WEIGHT, 4)

    # Step 3: Compute composite score
    rule_contribution = 0.0
    for rule_name, weight in RULE_WEIGHTS.items():
        factor = rule_results["factors"].get(rule_name, {})
        if factor.get("triggered", False):
            rule_contribution += weight

    composite_score = min(1.0, round(rule_contribution + ml_contribution, 4))

    # Step 4: Build explainable factors payload
    breakdown = {
        rule_name: {
            "weight": weight,
            "triggered": rule_results["factors"].get(rule_name, {}).get("triggered", False),
            "contribution": weight if rule_results["factors"].get(rule_name, {}).get("triggered", False) else 0.0,
        }
        for rule_name, weight in RULE_WEIGHTS.items()
    }
    breakdown["ml_anomaly"] = {
        "score": ml_score_val,
        "weight": ML_WEIGHT,
        "contribution": ml_contribution,
    }

    factors = {
        "rule_engine": rule_results["factors"],
        "triggered_rules": rule_results["triggered_rules"],
        "ml_score": ml_score_val,
        "ml_contribution": ml_contribution,
        "ml_features": ml_features,
        "composite_breakdown": breakdown,
    }

    model_version = f"rules_v1+{ML_MODEL_VERSION}" if ML_MODEL is not None else "rules_v1"

    # Step 5: Persist atomically
    with db_transaction.atomic():
        risk_score, created = RiskScore.objects.update_or_create(
            transaction=txn,
            defaults={
                "composite_score": composite_score,
                "model_version": model_version,
                "factors": factors,
            },
        )
        # Rules above read the pre-transaction baseline; now fold this txn in.
        # Lock the account row so concurrent workers don't lose updates.
        from accounts.models import Account
        locked_account = Account.objects.select_for_update().get(pk=account.pk)
        prior_count = (
            Transaction.objects.filter(account=locked_account, status=Transaction.Status.SCORED)
            .exclude(pk=txn.pk)
            .count()
        )
        locked_account.record_transaction(txn, prior_count)
        locked_account.save(update_fields=[
            "avg_spend", "spend_stddev", "last_known_lat", "last_known_lng",
            "last_transaction_at", "updated_at",
        ])

        txn.status = Transaction.Status.SCORED
        txn.save(update_fields=["status", "updated_at"])

    # Step 6: Trigger alert & real-time broadcast if composite score exceeds threshold
    from django.conf import settings
    from alerts.models import Alert
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    alert_id = None
    alert_created = False
    alert_threshold = getattr(settings, "RISK_SCORE_ALERT_THRESHOLD", 0.6)

    if composite_score >= alert_threshold:
        with db_transaction.atomic():
            alert, alert_created = Alert.objects.get_or_create(
                transaction=txn,
                risk_score=risk_score,
                defaults={"status": Alert.Status.PENDING},
            )
            alert_id = alert.id

        channel_layer = get_channel_layer()
        if channel_layer is not None:
            try:
                alert_payload = {
                    "type": "alert.broadcast",
                    "alert": {
                        "id": alert.id,
                        "transaction_id": txn.id,
                        "idempotency_key": txn.idempotency_key,
                        "account_number": getattr(account, "account_number", ""),
                        "amount": str(txn.amount),
                        "currency": txn.currency,
                        "merchant": txn.merchant,
                        "timestamp": txn.timestamp.isoformat(),
                        "composite_score": risk_score.composite_score,
                        "status": alert.status,
                        "factors": risk_score.factors,
                    },
                }
                async_to_sync(channel_layer.group_send)("analysts", alert_payload)
                logger.info(
                    "score_transaction: Broadcast alert #%s for txn %s to 'analysts' group",
                    alert.id,
                    transaction_id,
                )
            except Exception as e:
                logger.error("score_transaction: Failed to broadcast alert #%s: %s", alert.id, e)

    logger.info(
        "score_transaction: Transaction %s scored %.2f (rules: %s, ml_score: %.2f, alert: %s)",
        transaction_id,
        composite_score,
        rule_results["triggered_rules"],
        ml_score_val,
        alert_id,
    )

    return {
        "status": "scored",
        "transaction_id": transaction_id,
        "composite_score": composite_score,
        "triggered_rules": rule_results["triggered_rules"],
        "ml_score": ml_score_val,
        "alert_id": alert_id,
        "alert_created": alert_created,
    }


@shared_task(name="risk.retrain_model")
def retrain_model_task(trigger: str = "scheduled", force: bool = False) -> dict:
    """Celery entry point for retraining the ML model from analyst labels."""
    from risk.retraining import retrain
    return retrain(trigger=trigger, force=force)
