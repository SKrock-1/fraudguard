import logging
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDay, TruncHour, TruncMinute
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsAnalyst
from alerts.models import Alert
from alerts.serializers import AlertSerializer, AlertReviewSerializer
from audit.models import AuditLog
from risk.models import RiskScore
from transactions.models import Transaction

logger = logging.getLogger(__name__)


class AlertListView(generics.ListAPIView):
    """
    List alerts, optionally filtered by status (e.g. ?status=pending).
    Accessible by analyst and admin roles.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated, IsAnalyst]

    def get_queryset(self):
        qs = Alert.objects.select_related(
            "transaction", "transaction__account", "risk_score", "assigned_to"
        ).all()
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class AlertDetailView(generics.RetrieveAPIView):
    """
    Retrieve full details of a specific alert including factors breakdown.
    Accessible by analyst and admin roles.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated, IsAnalyst]
    lookup_url_kwarg = "alert_id"
    queryset = Alert.objects.select_related(
        "transaction", "transaction__account", "risk_score", "assigned_to"
    ).all()


class AlertReviewView(APIView):
    """
    POST /api/alerts/{id}/review/
    Approve or reject a flagged transaction alert.
    Restricted to analyst and admin roles.

    On review:
    1. Updates the Alert status (approved/rejected), timestamp, and notes.
    2. Writes an immutable AuditLog entry (actor, action, target, payload).
    """
    permission_classes = [IsAuthenticated, IsAnalyst]

    def post(self, request, alert_id: int):
        try:
            alert = Alert.objects.select_related("transaction", "risk_score").get(id=alert_id)
        except Alert.DoesNotExist:
            return Response(
                {"detail": f"Alert with ID {alert_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AlertReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        decision = serializer.validated_data["decision"]
        notes = serializer.validated_data.get("notes", "")
        new_status = Alert.Status.APPROVED if decision == "approved" else Alert.Status.REJECTED

        with db_transaction.atomic():
            # A decision is final: lock the row so two analysts reviewing at the
            # same moment cannot both succeed, then refuse anything not pending.
            # of=("self",): lock only the alert row. Postgres refuses FOR UPDATE on the
            # nullable side of the assigned_to outer join, and we don't need those rows locked.
            alert = (
                Alert.objects.select_for_update(of=("self",))
                .select_related("transaction", "risk_score", "assigned_to")
                .get(pk=alert.pk)
            )
            if alert.status != Alert.Status.PENDING:
                reviewer = alert.assigned_to.username if alert.assigned_to else "another analyst"
                return Response(
                    {
                        "detail": f"Alert #{alert.id} was already reviewed ({alert.status}) by {reviewer}.",
                        "alert": AlertSerializer(alert).data,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            previous_status = alert.status

            # 1. Update Alert
            alert.status = new_status
            alert.assigned_to = request.user
            alert.notes = notes
            alert.resolved_at = timezone.now()
            alert.save(update_fields=["status", "assigned_to", "notes", "resolved_at"])

            # 2. Write permanent insert-only AuditLog
            audit_payload = {
                "previous_status": previous_status,
                "new_status": new_status,
                "decision": decision,
                "notes": notes,
                "transaction_id": alert.transaction.id,
                "idempotency_key": alert.transaction.idempotency_key,
                "amount": str(alert.transaction.amount),
                "composite_score": alert.risk_score.composite_score,
            }
            audit_entry = AuditLog.objects.create(
                actor=request.user,
                action=f"alert_{decision}",
                target=f"Alert:{alert.id}",
                payload=audit_payload,
            )

        logger.info(
            "Alert #%s reviewed by %s: %s -> %s (AuditLog #%s)",
            alert.id,
            request.user.username,
            previous_status,
            new_status,
            audit_entry.id,
        )

        return Response(
            {
                "status": "success",
                "alert": AlertSerializer(alert).data,
                "audit_log_id": audit_entry.id,
            },
            status=status.HTTP_200_OK,
        )


STATS_WINDOWS = {
    # window -> (lookback, bucket size, Trunc function name)
    "1h": (timedelta(hours=1), timedelta(minutes=1), "minute"),
    "24h": (timedelta(hours=24), timedelta(hours=1), "hour"),
    "7d": (timedelta(days=7), timedelta(days=1), "day"),
}
HISTOGRAM_BINS = 20


class AlertStatsView(APIView):
    """
    GET /api/alerts/stats/?window=1h|24h|7d
    Aggregates for the analyst dashboard: totals, a transactions/alerts time
    series, the composite score distribution and how often each rule fired.
    """
    permission_classes = [IsAuthenticated, IsAnalyst]

    def get(self, request):
        window = request.query_params.get("window", "24h")
        if window not in STATS_WINDOWS:
            return Response(
                {"detail": f"window must be one of {sorted(STATS_WINDOWS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lookback, bucket, trunc = STATS_WINDOWS[window]
        now = timezone.now()
        since = now - lookback
        trunc_fn = {"minute": TruncMinute, "hour": TruncHour, "day": TruncDay}[trunc]

        txns = Transaction.objects.filter(timestamp__gte=since)
        alerts = Alert.objects.filter(transaction__timestamp__gte=since)
        status_counts = dict(alerts.order_by().values_list("status").annotate(n=Count("id")))
        scores = RiskScore.objects.filter(transaction__timestamp__gte=since)
        score_agg = scores.aggregate(avg=Avg("composite_score"), n=Count("id"))

        # Time series, with empty buckets filled so the chart has a continuous x-axis
        txn_series = dict(
            txns.order_by().annotate(b=trunc_fn("timestamp")).values_list("b").annotate(n=Count("id"))
        )
        alert_series = dict(
            alerts.order_by().annotate(b=trunc_fn("transaction__timestamp")).values_list("b").annotate(n=Count("id"))
        )
        start = _bucket_floor(since, trunc)
        series = []
        t = start
        while t <= now:
            series.append({
                "t": t.isoformat(),
                "transactions": txn_series.get(t, 0),
                "alerts": alert_series.get(t, 0),
            })
            t += bucket

        # Score histogram and rule trigger counts are computed in Python from the
        # factors JSON, which keeps this portable across SQLite and Postgres.
        histogram = [0] * HISTOGRAM_BINS
        rule_counts = {"velocity": 0, "impossible_travel": 0, "amount_anomaly": 0, "ml_anomaly": 0}
        for score, factors in scores.values_list("composite_score", "factors").iterator():
            histogram[min(int(score * HISTOGRAM_BINS), HISTOGRAM_BINS - 1)] += 1
            for rule in (factors or {}).get("triggered_rules", []):
                if rule in rule_counts:
                    rule_counts[rule] += 1
            if (factors or {}).get("ml_score", 0) >= 0.5:
                rule_counts["ml_anomaly"] += 1

        resolved = alerts.filter(resolved_at__isnull=False)
        total_alerts = sum(status_counts.values())
        return Response({
            "window": window,
            "generated_at": now.isoformat(),
            "threshold": getattr(settings, "RISK_SCORE_ALERT_THRESHOLD", 0.6),
            "totals": {
                "transactions": txns.count(),
                "scored": score_agg["n"],
                "alerts": total_alerts,
                "pending": status_counts.get(Alert.Status.PENDING, 0),
                "approved": status_counts.get(Alert.Status.APPROVED, 0),
                "rejected": status_counts.get(Alert.Status.REJECTED, 0),
                "avg_score": round(score_agg["avg"] or 0.0, 4),
                "alert_rate": round(total_alerts / score_agg["n"], 4) if score_agg["n"] else 0.0,
                "flagged_amount": str(alerts.aggregate(s=Sum("transaction__amount"))["s"] or 0),
                "blocked_amount": str(
                    alerts.filter(status=Alert.Status.REJECTED).aggregate(s=Sum("transaction__amount"))["s"] or 0
                ),
                "resolved": resolved.count(),
            },
            "series": series,
            "score_histogram": [
                {"start": i / HISTOGRAM_BINS, "end": (i + 1) / HISTOGRAM_BINS, "count": n}
                for i, n in enumerate(histogram)
            ],
            "rule_triggers": [{"rule": rule, "count": n} for rule, n in rule_counts.items()],
        })


def _bucket_floor(dt, unit):
    """Floor a datetime to the start of its minute/hour/day bucket (UTC)."""
    dt = dt.astimezone(dt_timezone.utc)
    if unit == "minute":
        return dt.replace(second=0, microsecond=0)
    if unit == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)
