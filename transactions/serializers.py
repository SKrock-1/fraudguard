from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from accounts.models import Account
from transactions.models import Transaction


class TransactionResponseSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source="account.account_number", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account_number",
            "amount",
            "currency",
            "merchant",
            "lat",
            "lng",
            "timestamp",
            "idempotency_key",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class TransactionIngestionSerializer(serializers.Serializer):
    account_number = serializers.CharField(
        max_length=64,
        required=True,
        help_text="Account number for which transaction is created",
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=True,
    )
    currency = serializers.CharField(
        max_length=3,
        default="USD",
        required=False,
    )
    merchant = serializers.CharField(
        max_length=255,
        required=True,
    )
    lat = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    lng = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    timestamp = serializers.DateTimeField(
        required=False,
        default=timezone.now,
    )
    idempotency_key = serializers.CharField(
        max_length=128,
        required=True,
        allow_blank=False,
        help_text="Unique client-supplied idempotency key",
    )

    def validate_account_number(self, value):
        try:
            return Account.objects.get(account_number=value)
        except Account.DoesNotExist:
            raise serializers.ValidationError(f"Account '{value}' does not exist.")

    def validate_currency(self, value):
        return value.upper()
