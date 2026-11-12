from django.db import models
from transactions.models import Transaction


class RiskScore(models.Model):
    """
    Stores the composite fraud risk score for a transaction, with an
    explainable breakdown of contributing factors in a JSONField.

    Created by the scoring pipeline (Celery task) after rule engine and
    ML scorer evaluation.
    """
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name="risk_score",
        help_text="The transaction this score evaluates",
    )
    composite_score = models.FloatField(
        help_text="Combined risk score from 0.0 (safe) to 1.0 (high risk)",
    )
    model_version = models.CharField(
        max_length=64,
        default="rules_v1",
        help_text="Version identifier for the scoring model/pipeline",
    )
    factors = models.JSONField(
        default=dict,
        help_text="Explainable breakdown: each rule/model contribution to the score",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["composite_score"], name="idx_riskscore_composite"),
        ]

    def __str__(self):
        return (
            f"RiskScore(txn={self.transaction.idempotency_key[:12]}..., "
            f"score={self.composite_score:.2f}, model={self.model_version})"
        )


class ModelVersion(models.Model):
    """
    One retraining run of the ML anomaly model. Every run is recorded, whether
    or not its challenger model was promoted to production.
    """

    class Trigger(models.TextChoices):
        MANUAL = "manual", "Manual (command line)"
        API = "api", "Admin API"
        SCHEDULED = "scheduled", "Scheduled job"

    version = models.CharField(max_length=64, unique=True)
    trained_at = models.DateTimeField(auto_now_add=True, db_index=True)
    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.MANUAL)
    promoted = models.BooleanField(default=False, help_text="Whether this model replaced the production model")
    train_samples = models.PositiveIntegerField(default=0)
    labeled_fraud = models.PositiveIntegerField(default=0, help_text="Alerts analysts confirmed as fraud")
    labeled_legit = models.PositiveIntegerField(default=0, help_text="Alerts analysts approved as legitimate")
    contamination = models.FloatField(default=0.02)
    metrics = models.JSONField(default=dict, help_text="Champion vs challenger evaluation on the holdout set")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="model_versions",
    )
    artifact = models.BinaryField(
        null=True, blank=True, editable=False,
        help_text="joblib bundle of a promoted model; stored in the database so it survives ephemeral disks",
    )

    class Meta:
        ordering = ["-trained_at"]

    def __str__(self):
        return f"ModelVersion({self.version}, promoted={self.promoted})"
