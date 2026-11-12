from django.contrib import admin
from transactions.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "idempotency_key",
        "account",
        "amount",
        "currency",
        "merchant",
        "status",
        "timestamp",
        "created_at",
    )
    list_filter = ("status", "currency", "created_at")
    search_fields = ("idempotency_key", "merchant", "account__account_number")
    readonly_fields = ("created_at", "updated_at")
