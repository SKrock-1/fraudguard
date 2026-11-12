from decimal import Decimal
from django.db import models
from django.utils import timezone
from accounts.models import Account


class Transaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SCORED = "scored", "Scored"

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transactions",
        help_text="Account associated with this transaction",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Transaction monetary amount",
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO 4217 3-letter currency code",
    )
    merchant = models.CharField(
        max_length=255,
        help_text="Merchant or counterparty name",
    )
    lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude of transaction event",
    )
    lng = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude of transaction event",
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Timestamp when the transaction occurred",
    )
    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Unique client-supplied idempotency key for deduplication",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Scoring pipeline status: pending or scored",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["account", "timestamp"], name="idx_txn_account_timestamp"),
            models.Index(fields=["idempotency_key"], name="idx_txn_idempotency_key"),
        ]

    def __str__(self):
        return f"Txn {self.idempotency_key[:12]}... - {self.currency} {self.amount} ({self.status})"
