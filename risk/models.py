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
