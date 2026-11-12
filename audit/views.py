from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsAnalyst
from audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "actor_username", "action", "target", "payload", "timestamp"]
        read_only_fields = fields


class AuditLogListView(generics.ListAPIView):
    """
    GET /api/audit/?target=Alert:42&limit=100
    Read-only view of the insert-only audit trail, newest first.
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAnalyst]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor").order_by("-timestamp", "-id")
        target = self.request.query_params.get("target")
        if target:
            qs = qs.filter(target=target)
        try:
            limit = min(max(int(self.request.query_params.get("limit", 200)), 1), 1000)
        except ValueError:
            limit = 200
        return qs[:limit]
