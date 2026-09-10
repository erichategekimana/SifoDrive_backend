"""
apps/notifications/providers/factory.py
=======================================
Factory function to instantiate the configured SMS provider.
"""

import logging
from typing import Optional
from django.conf import settings

from apps.notifications.providers.base import BaseSMSProvider
from apps.notifications.providers.console import ConsoleSMSProvider
from apps.notifications.providers.pindo import PindoSMSProvider
from apps.notifications.providers.africas_talking import AfricasTalkingSMSProvider
from apps.notifications.providers.http_gateway import HttpGatewaySMSProvider

logger = logging.getLogger("apps.notifications.sms.factory")

_PROVIDER_MAP = {
    "console": ConsoleSMSProvider,
    "mock": ConsoleSMSProvider,
    "pindo": PindoSMSProvider,
    "africas_talking": AfricasTalkingSMSProvider,
    "http_gateway": HttpGatewaySMSProvider,
    "webhook": HttpGatewaySMSProvider,
}


def get_sms_provider(provider_name: Optional[str] = None) -> BaseSMSProvider:
    """
    Return an instance of the configured SMS provider.

    Resolution order:
    1. Explicit provider_name parameter
    2. settings.SMS_PROVIDER
    3. Fallback to ConsoleSMSProvider
    """
    key = (provider_name or getattr(settings, "SMS_PROVIDER", "console")).strip().lower()
    provider_class = _PROVIDER_MAP.get(key)

    if provider_class:
        return provider_class()

    logger.warning(
        "Unknown SMS_PROVIDER '%s'. Falling back to ConsoleSMSProvider.",
        key,
    )
    return ConsoleSMSProvider()
