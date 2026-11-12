from django.db import models
from django.conf import settings
from django.core.exceptions import PermissionDenied


class AuditLog(models.Model):
    """
    Append-only audit trail recording all analyst decisions and security events.
    Enforced insert-only at both application level and database level.
    """
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="User who performed the action",
    )
    action = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Action identifier (e.g. alert_approved, alert_rejected)",
    )
    target = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Target resource identifier (e.g. Alert:42, Rule:velocity)",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Event context, decision parameters, previous/new states",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the event occurred",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["action", "timestamp"], name="idx_audit_action_time"),
            models.Index(fields=["target", "timestamp"], name="idx_audit_target_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and not kwargs.get("force_insert", False):
            raise PermissionDenied("AuditLog is insert-only; existing records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("AuditLog is insert-only; records cannot be deleted.")

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"[{self.timestamp.isoformat()}] {actor_name} -> {self.action} on {self.target}"
