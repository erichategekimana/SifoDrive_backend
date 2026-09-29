import logging
from django.contrib.auth import get_user_model

from apps.core.exceptions import UserNotFoundException
from apps.core.utils import normalize_phone_number

User = get_user_model()
logger = logging.getLogger(__name__)


class UserService:
    """CRUD and lifecycle operations for user accounts."""

    @classmethod
    def get_by_phone(cls, phone_number: str) -> User:
        """Fetch a user by phone number. Raises UserNotFoundException if not found."""
        normalized = normalize_phone_number(phone_number)
        if not normalized:
            raise UserNotFoundException()
        try:
            return User.objects.get(phone_number=normalized)
        except User.DoesNotExist:
            raise UserNotFoundException()

    @classmethod
    def get_by_id(cls, user_id: str) -> User:
        """Fetch a user by UUID. Raises UserNotFoundException if not found."""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise UserNotFoundException()

    @classmethod
    def suspend_user(cls, user: User, suspended_by: User) -> User:
        """Suspend a user account. Logs the action."""
        user.suspend()
        logger.warning(
            "User suspended | target=%s by_admin=%s",
            str(user.id)[:8],
            str(suspended_by.id)[:8],
        )
        return user

    @classmethod
    def promote_to_role(cls, user: User, new_role: str, promoted_by: User) -> User:
        """
        Change a user's role. Only SYSTEM_ADMIN is authorised to call this.
        Records an immutable audit log entry.
        """
        old_role = user.role
        user.role = new_role
        user.save(update_fields=["role"])

        from apps.audit.services import AuditService
        AuditService.log_role_change(
            target_user=user,
            old_role=old_role,
            new_role=new_role,
            performed_by=promoted_by,
        )
        return user
