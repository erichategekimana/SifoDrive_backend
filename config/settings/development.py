"""
Sifo Drive — Development Settings
===================================
Extends base.py with developer-friendly overrides:
- Debug enabled
- Debug Toolbar
- Verbose SQL logging
- Relaxed security for local dev
"""

from .base import *  # noqa: F401, F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]

import sys

# --- Development-Only Apps ---
if not any("test" in arg for arg in sys.argv):
    INSTALLED_APPS += [  # noqa: F405
        "debug_toolbar",
    ]
    MIDDLEWARE = [  # noqa: F405
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ] + MIDDLEWARE  # noqa: F405

INSTALLED_APPS += [  # noqa: F405
    "django_extensions",
]

# --- Debug Toolbar (only shows for internal IPs) ---
INTERNAL_IPS = ["127.0.0.1", "localhost"]

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
    "SHOW_COLLAPSED": True,
    "SQL_WARNING_THRESHOLD": 100,   # Warn on queries > 100ms
    "IS_RUNNING_TESTS": False,
}

# --- SQL Logging (Enable to see all queries in console) ---
LOGGING["loggers"]["django.db.backends"]["level"] = "DEBUG"  # noqa: F405

# --- CORS: Allow all origins in dev ---
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# --- Email (Console backend for dev — no real emails sent) ---
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- Celery: Run tasks synchronously in dev (set to False to use real broker) ---
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = True

# --- Use local file storage in dev (no MinIO required) ---
USE_MINIO = False
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# --- Relaxed password validation in dev ---
AUTH_PASSWORD_VALIDATORS = []

# --- DRF: Include Browsable API in dev ---
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",  # Dev only
    ],
    # Relax throttling for development
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/hour",
        "user": "100000/hour",
        "otp": "1000/hour",
        "payment": "1000/hour",
    },
}

# --- Cache & Sessions: In-memory cache & database sessions for dev (no Redis required) ---
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sifo-dev-cache",
        "KEY_PREFIX": "sifo",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
