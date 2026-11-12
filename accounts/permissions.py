from rest_framework.permissions import BasePermission
from accounts.models import User


class IsIngestionClient(BasePermission):
    """
    Allows access only to authenticated users with role 'ingestion_client' or 'admin'.
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role in (User.Role.INGESTION_CLIENT, User.Role.ADMIN) or request.user.is_superuser)
        )


class IsAnalyst(BasePermission):
    """
    Allows access only to authenticated users with role 'analyst' or 'admin'.
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role in (User.Role.ANALYST, User.Role.ADMIN) or request.user.is_superuser)
        )


class IsAdminRole(BasePermission):
    """
    Allows access only to authenticated users with role 'admin'.
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role == User.Role.ADMIN or request.user.is_superuser)
        )
