"""
apps/accounts/signals.py
=========================
Django signal handlers for the accounts app.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def log_user_creation(sender, instance, created, **kwargs):
    """Log new user creation for audit trail."""
    if created:
        logger.info(
            "New user created: id=%s role=%s phone=%s",
            str(instance.id)[:8],
            instance.role,
            instance.phone_number[-4:],  # Log only last 4 digits for privacy
        )
