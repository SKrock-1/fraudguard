import logging

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from risk.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """
    GET /api/health/ — liveness probe for Render / UptimeRobot / docker compose.

    Checks the database and Redis. Pass ?worker=1 to also ping the Celery
    worker (slower, up to HEALTH_WORKER_PING_TIMEOUT; skipped when tasks run eagerly). Returns 503 if any
    check fails so the platform treats the instance as unhealthy.
    """
    checks = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Health check: database unreachable: %s", exc)
        checks["database"] = "error"

    try:
        get_redis_client().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("Health check: redis unreachable: %s", exc)
        checks["redis"] = "error"

    if request.query_params.get("worker") in ("1", "true"):
        if settings.CELERY_TASK_ALWAYS_EAGER:
            checks["worker"] = "eager"
        else:
            from fraudguard.celery import app as celery_app
            try:
                # Free instances get a fraction of a CPU; a 1 s ping flaps there
                replies = celery_app.control.ping(timeout=settings.HEALTH_WORKER_PING_TIMEOUT)
                checks["worker"] = "ok" if replies else "error"
            except Exception as exc:
                logger.error("Health check: celery ping failed: %s", exc)
                checks["worker"] = "error"

    healthy = all(value in ("ok", "eager") for value in checks.values())
    return Response(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
