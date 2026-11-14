from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminRole, IsAnalyst
from risk.models import ModelVersion
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


class ModelVersionSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None, read_only=True)

    class Meta:
        model = ModelVersion
        fields = [
            "id", "version", "trained_at", "trigger", "promoted", "train_samples",
            "labeled_fraud", "labeled_legit", "contamination", "metrics", "notes", "created_by",
        ]


class ModelVersionListView(APIView):
    """GET /api/ml/models/ -> the production model and the last 20 retraining runs."""
    permission_classes = [IsAuthenticated, IsAnalyst]

    def get(self, request):
        import risk.tasks as tasks
        tasks.refresh_model()
        runs = ModelVersion.objects.select_related("created_by")[:20]
        return Response({
            "production_version": tasks.ML_MODEL_VERSION if tasks.ML_MODEL is not None else None,
            "runs": ModelVersionSerializer(runs, many=True).data,
        })


class RetrainSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False)
    dry_run = serializers.BooleanField(default=False)
    trigger = serializers.ChoiceField(choices=[ModelVersion.Trigger.API, ModelVersion.Trigger.SCHEDULED], default=ModelVersion.Trigger.API)


class RetrainView(APIView):
    """POST /api/ml/retrain/ (admin) -> run one champion/challenger retraining cycle."""
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        from risk.retraining import retrain
        serializer = RetrainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = retrain(user=request.user, **serializer.validated_data)
        code = status.HTTP_200_OK if result["status"] != "skipped" else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(result, status=code)


class BacktestView(APIView):
    """
    GET /api/ml/backtest/?source=analyst|synthetic
    Precision / recall / F1 for every alert threshold, plus a score histogram
    split by label. `analyst` uses stored scores labelled by review decisions.
    """
    permission_classes = [IsAuthenticated, IsAnalyst]

    def get(self, request):
        from risk import backtest
        threshold = getattr(settings, "RISK_SCORE_ALERT_THRESHOLD", 0.6)
        source = request.query_params.get("source", "analyst")
        if source == "synthetic":
            return Response(backtest.synthetic_backtest(threshold))
        if source == "analyst":
            return Response(backtest.analyst_backtest(threshold))
        return Response({"detail": "source must be 'analyst' or 'synthetic'."}, status=status.HTTP_400_BAD_REQUEST)
