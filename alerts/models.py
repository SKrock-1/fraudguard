from django.db import models
from django.conf import settings
from transactions.models import Transaction
from risk.models import RiskScore


class Alert(models.Model):
    """
    Represents a high-risk transaction alert requiring human or automated review.
    Created when a transaction's composite risk score exceeds the alert threshold.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved (Legitimate)"
        REJECTED = "rejected", "Rejected (Fraudulent)"

    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name="alert",
        help_text="The flagged transaction",
    )
    risk_score = models.OneToOneField(
        RiskScore,
        on_delete=models.CASCADE,
        related_name="alert",
        help_text="The risk score that triggered this alert",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Review status: pending, approved, or rejected",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_alerts",
        help_text="Analyst assigned to review this alert",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Analyst notes or resolution rationale",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_alert_status_created"),
        ]

    def __str__(self):
        return f"Alert #{self.id} (txn={self.transaction.idempotency_key[:12]}..., status={self.status})"
