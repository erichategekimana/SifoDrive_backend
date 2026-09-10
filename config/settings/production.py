"""
Sifo Drive — Production Settings
===================================
Extends base.py with hardened security, MinIO storage,
Sentry error tracking, and Gunicorn-ready configuration.
"""

from .base import *  # noqa: F401, F403
from .base import env

DEBUG = False

# --- Strict Security Headers ---
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000           # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True               # Force HTTPS
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

# --- File Storage: MinIO ---
USE_MINIO = True

# --- Email (SMTP for production) ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@sifodrive.rw")

# --- Sentry Error Tracking ---
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,       # 10% performance sampling
        send_default_pii=False,       # NEVER send PII to Sentry (NCSA compliance)
        environment="production",
    )

# --- Cache: Redis with connection pooling ---
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressor.zlib.ZlibCompressor",
            "CONNECTION_POOL_KWARGS": {"max_connections": 50},
        },
        "KEY_PREFIX": "sifo_prod",
        "TIMEOUT": 600,  # 10 minutes
    }
}

# --- Production Logging (stderr → systemd journal / log aggregator) ---
LOGGING["handlers"]["console"]["filters"] = []           # noqa: F405
LOGGING["handlers"]["console"]["level"] = "WARNING"      # noqa: F405
