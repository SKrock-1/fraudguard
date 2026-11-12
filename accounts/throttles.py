"""
Per-API-client throttling for the FraudGuard ingestion endpoint.

Uses the authenticated user's primary key as the throttle identity,
so each API client (B2B integration) is rate-limited independently.
"""
from rest_framework.throttling import SimpleRateThrottle


class PerClientIngestionThrottle(SimpleRateThrottle):
    """
    Throttle ingestion requests per authenticated API client.

    Rate is configured via REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['ingestion']
    e.g. '100/minute'.
    """
    scope = "ingestion"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return self.cache_format % {
                "scope": self.scope,
                "ident": request.user.pk,
            }
        # Unauthenticated requests get throttled by IP
        return self.get_ident(request)
