"""
WebSocket consumer for real-time fraud alert broadcasting.

Restricted to users with 'analyst' or 'admin' roles.
Joins the 'analysts' group on connect and streams newly triggered alerts.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)

ANALYSTS_GROUP = "analysts"
ALLOWED_ROLES = {"analyst", "admin"}


class AlertConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer handling real-time alert broadcasts to connected analysts.
    """
    async def connect(self):
        user = self.scope.get("user")

        # Reject unauthenticated connections or unauthorized roles
        if not user or not user.is_authenticated or getattr(user, "role", None) not in ALLOWED_ROLES:
            logger.warning("Rejecting WebSocket connection: unauthenticated or unauthorized role (%s)", getattr(user, "role", None))
            await self.close(code=4003)
            return

        # Join the analysts broadcast group
        self.group_name = ANALYSTS_GROUP
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("Analyst %s connected to alert stream", user.username)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info("Analyst disconnected from alert stream (code: %s)", close_code)

    async def alert_broadcast(self, event):
        """
        Handler for group messages sent via channel_layer.group_send('analysts', ...).
        Sends the JSON alert payload down to the connected WebSocket client.
        """
        await self.send_json(event.get("alert", {}))
