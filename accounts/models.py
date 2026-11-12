from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class User(AbstractUser):
    class Role(models.TextChoices):
        INGESTION_CLIENT = "ingestion_client", "Ingestion Client"
        ANALYST = "analyst", "Analyst"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.INGESTION_CLIENT,
        help_text="User role in FraudGuard system: ingestion_client, analyst, or admin.",
    )

    def is_ingestion_client(self) -> bool:
        return self.role == self.Role.INGESTION_CLIENT or self.is_superuser

    def is_analyst(self) -> bool:
        return self.role == self.Role.ANALYST or self.is_superuser

    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    def __str__(self):
        return f"{self.username} ({self.role})"


class Account(models.Model):
    """
    Represents a financial account with rolling spend and location profile.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    account_number = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="External or internal unique account identifier",
    )
    avg_spend = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Rolling average transaction amount",
    )
    spend_stddev = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Standard deviation of transaction amounts",
    )
    last_known_lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude of latest confirmed transaction",
    )
    last_known_lng = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude of latest confirmed transaction",
    )
    last_transaction_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of latest transaction",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def record_transaction(self, transaction, prior_count: int) -> None:
        """
        Fold a newly scored transaction into the rolling spend/location profile.

        Uses Welford's incremental update so no transaction history is re-read:
        `prior_count` is the number of transactions already reflected in
        avg_spend/spend_stddev (population stddev). Caller is responsible for
        locking the row (select_for_update) and saving.
        """
        amount = float(transaction.amount)
        mean = float(self.avg_spend)
        m2 = float(self.spend_stddev) ** 2 * prior_count

        n = prior_count + 1
        new_mean = mean + (amount - mean) / n
        m2 += (amount - mean) * (amount - new_mean)

        self.avg_spend = Decimal(str(round(new_mean, 2)))
        self.spend_stddev = Decimal(str(round((m2 / n) ** 0.5, 2)))

        # Ignore out-of-order events so a late-arriving old transaction can't
        # rewind the location baseline used by the impossible-travel rule.
        if self.last_transaction_at is None or transaction.timestamp >= self.last_transaction_at:
            self.last_transaction_at = transaction.timestamp
            if transaction.lat is not None and transaction.lng is not None:
                self.last_known_lat = transaction.lat
                self.last_known_lng = transaction.lng

    def __str__(self):
        return f"Account {self.account_number} (User: {self.user.username})"
