"""
ASGI config for fraudguard project.

Exposes the ASGI callable as a module-level variable named `application`,
routing HTTP traffic to Django ASGI and WebSocket traffic to Channels with
JWT authentication middleware.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fraudguard.settings")
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from alerts.middleware import JWTAuthMiddlewareStack
import alerts.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(alerts.routing.websocket_urlpatterns)
    ),
})
