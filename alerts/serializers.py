from rest_framework import serializers
from alerts.models import Alert
from transactions.serializers import TransactionResponseSerializer as TransactionSerializer
from risk.models import RiskScore


class RiskScoreSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskScore
        fields = ["id", "composite_score", "model_version", "factors", "created_at"]


class AlertSerializer(serializers.ModelSerializer):
    transaction = TransactionSerializer(read_only=True)
    risk_score = RiskScoreSimpleSerializer(read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "transaction",
            "risk_score",
            "status",
            "assigned_to",
            "assigned_to_username",
            "notes",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = ["id", "transaction", "risk_score", "created_at", "resolved_at"]


class AlertReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["approved", "rejected"],
        help_text="Review decision: 'approved' (legitimate transaction) or 'rejected' (confirmed fraud)",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Analyst notes explaining the decision rationale",
    )
