from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAnalyst
from risk import simulator


class SimulateTrafficSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1, max_value=200, default=30)
    fraud_rate = serializers.FloatField(min_value=0.0, max_value=1.0, default=0.25)
    duration_seconds = serializers.FloatField(min_value=1.0, max_value=300.0, default=30.0)


class SimulateTrafficView(APIView):
    """
    GET  /api/demo/simulate/ -> {"enabled": bool, "running": bool}
    POST /api/demo/simulate/ -> start streaming synthetic transactions for a demo.

    Only available when DEMO_TOOLS_ENABLED is on (defaults to DEBUG).
    """
    permission_classes = [IsAuthenticated, IsAnalyst]

    def get(self, request):
        return Response({
            "enabled": settings.DEMO_TOOLS_ENABLED,
            "running": simulator.stream_running(),
        })

    def post(self, request):
        if not settings.DEMO_TOOLS_ENABLED:
            return Response({"detail": "Demo tools are disabled."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SimulateTrafficSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not simulator.start_live_stream(**serializer.validated_data):
            return Response({"detail": "A simulation is already running."}, status=status.HTTP_409_CONFLICT)
        return Response({"status": "started", **serializer.validated_data}, status=status.HTTP_202_ACCEPTED)
