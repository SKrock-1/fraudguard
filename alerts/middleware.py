"""
WebSocket JWT Authentication Middleware for Django Channels.

Allows analysts and admins to authenticate WebSocket connections via:
1. Query string: ?token=<access_token>
2. Authorization header: Bearer <access_token>
3. Standard Django session if already logged in
"""
import logging
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_str: str):
    """Validate a SimpleJWT access token and return the associated User."""
    try:
        token = AccessToken(token_str)
        user_id = token.get("user_id")
        if user_id:
            return User.objects.get(id=user_id)
    except Exception as e:
        logger.debug("WebSocket JWT validation failed: %s", e)
    return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Middleware that populates scope["user"] from JWT token in query string or headers.
    """
    async def __call__(self, scope, receive, send):
        # 1. Check query string: ?token=<jwt>
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        # 2. Check headers: Authorization: Bearer <jwt>
        if not token:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1].strip()

        # 3. Resolve user if token is present
        if token:
            scope["user"] = await get_user_from_token(token)
        elif "user" not in scope or not scope["user"].is_authenticated:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    from channels.auth import AuthMiddlewareStack
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
