"""
Sifo Drive — Base Django Settings
==================================
Shared configuration for all environments.
Environment-specific files (development.py, staging.py, production.py)
extend and override these values.
"""

from datetime import timedelta
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Path & Environment Setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # SifoDrive_backend/
APPS_DIR = BASE_DIR / "apps"

env = environ.Env(
    DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    LOG_LEVEL=(str, "INFO"),
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES=(int, 60),
    JWT_REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
    PROCTORING_SNAPSHOT_RETENTION_DAYS=(int, 30),
    IREMBO_BOOKING_RETENTION_DAYS=(int, 365),
)

# Read .env file if it exists (silently skip in production containers)
environ.Env.read_env(BASE_DIR / ".env", overwrite=True)


# ---------------------------------------------------------------------------
# Core Django Settings
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
ROOT_URLCONF = "config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Application Definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.lms",
    "apps.examinations",
    "apps.live_classes",
    "apps.booking",
    "apps.payments",
    "apps.notifications",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # Must be before CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditLogMiddleware",  # Immutable audit logging
]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database — PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="sifo_drive_db"),
        "USER": env("DB_USER", default="sifo_user"),
        "PASSWORD": env("DB_PASSWORD", default="sifo_password"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        "ATOMIC_REQUESTS": True,  # Wrap every request in a transaction
        "CONN_MAX_AGE": 60,
        "OPTIONS": {},
    }
}


# ---------------------------------------------------------------------------
# Cache — Redis
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "sifo",
        "TIMEOUT": 300,  # 5 minutes default
    }
}
SESSION_ENGINE = env("SESSION_ENGINE", default="django.contrib.sessions.backends.cached_db")
SESSION_CACHE_ALIAS = "default"


# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"


# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",   # Argon2 (most secure)
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kigali"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & Media Files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/hour",
        "user": "1000/hour",
        "otp": "5/hour",       # Strict OTP rate limiting
        "payment": "30/hour",  # Payment initiation
    },
}


# ---------------------------------------------------------------------------
# JWT Configuration
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env("JWT_ACCESS_TOKEN_LIFETIME_MINUTES")
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env("JWT_REFRESH_TOKEN_LIFETIME_DAYS")
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.CustomTokenObtainPairSerializer",
}


# ---------------------------------------------------------------------------
# DRF Spectacular (API Documentation)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "Sifo Drive API",
    "DESCRIPTION": (
        "Sifo Drive — Digital Driving Academy, Certified Practice Examination Portal, "
        "and Irembo Physical Test Booking Concierge.\n\n"
        "**Version:** 3.0 | **Status:** Active Development"
    ),
    "VERSION": "3.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}


# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-device-fingerprint",  # For exam proctoring device verification
]


# ---------------------------------------------------------------------------
# Celery (Async Task Queue)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60          # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60     # 25 minutes soft limit
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_RESULT_EXTENDED = True
CELERY_TASK_ACKS_LATE = True              # Ack after task completion (safer)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


# ---------------------------------------------------------------------------
# File Storage (MinIO / S3-compatible)
# ---------------------------------------------------------------------------
USE_MINIO = env.bool("USE_MINIO", default=False)

if USE_MINIO:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL")
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_QUERYSTRING_AUTH = True        # Signed URLs for private media
    AWS_QUERYSTRING_EXPIRE = 3600      # 1 hour signed URL expiry


# ---------------------------------------------------------------------------
# PII Encryption (AES-256 via Fernet for National ID columns)
# ---------------------------------------------------------------------------
PII_ENCRYPTION_KEY = env("PII_ENCRYPTION_KEY", default="")


# ---------------------------------------------------------------------------
# SMS & Notifications Configuration
# ---------------------------------------------------------------------------
SMS_PROVIDER = env("SMS_PROVIDER", default="console")  # console | pindo | africas_talking | http_gateway
SMS_GATEWAY_URL = env("SMS_GATEWAY_URL", default="")
SMS_API_KEY = env("SMS_API_KEY", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="PindoTest")
OTP_EXPIRY_MINUTES = env.int("OTP_EXPIRY_MINUTES", default=10)

# Local Rwanda Gateway (Pindo: https://api.pindo.io)
PINDO_API_TOKEN = env("PINDO_API_TOKEN", default="") or env("SMS_API_KEY", default="")

# Africa's Talking Gateway
AFRICAS_TALKING_USERNAME = env("AFRICAS_TALKING_USERNAME", default="")
AFRICAS_TALKING_API_KEY = env("AFRICAS_TALKING_API_KEY", default="")


# ---------------------------------------------------------------------------
# Mobile Money — MTN
# ---------------------------------------------------------------------------
MTN_MOMO = {
    "BASE_URL": env("MTN_MOMO_BASE_URL", default="https://sandbox.momodeveloper.mtn.com"),
    "SUBSCRIPTION_KEY": env("MTN_MOMO_SUBSCRIPTION_KEY", default=""),
    "API_USER": env("MTN_MOMO_API_USER", default=""),
    "API_KEY": env("MTN_MOMO_API_KEY", default=""),
    "ENVIRONMENT": env("MTN_MOMO_ENVIRONMENT", default="sandbox"),
    "CURRENCY": "RWF",
    "CALLBACK_HOST": env("FRONTEND_URL", default="http://localhost:3000"),
}

# Mobile Money — Airtel
AIRTEL_MONEY = {
    "BASE_URL": env("AIRTEL_MONEY_BASE_URL", default="https://openapi.airtel.africa"),
    "CLIENT_ID": env("AIRTEL_MONEY_CLIENT_ID", default=""),
    "CLIENT_SECRET": env("AIRTEL_MONEY_CLIENT_SECRET", default=""),
    "ENVIRONMENT": env("AIRTEL_MONEY_ENVIRONMENT", default="sandbox"),
    "CURRENCY": "RWF",
    "COUNTRY": "RW",
}


# ---------------------------------------------------------------------------
# Compliance & Data Retention (Rwanda Law No 058/2021)
# ---------------------------------------------------------------------------
COMPLIANCE = {
    "PROCTORING_SNAPSHOT_RETENTION_DAYS": env("PROCTORING_SNAPSHOT_RETENTION_DAYS"),
    "IREMBO_BOOKING_RETENTION_DAYS": env("IREMBO_BOOKING_RETENTION_DAYS"),
    "AUDIT_LOG_RETENTION_YEARS": 7,          # Immutable audit logs kept 7 years
    "OTP_ATTEMPT_LIMIT": 5,
    "OTP_LOCKOUT_MINUTES": 30,
    "EXAM_MAX_VIOLATIONS_BEFORE_FLAG": 3,    # Proctoring violation threshold
    "EXAM_SNAPSHOT_INTERVAL_SECONDS": 20,    # Webcam snapshot frequency
}


# ---------------------------------------------------------------------------
# Logging (Structured)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
        "json": {
            "()": "structlog.stdlib.ProcessorFormatter",
            "processor": "structlog.dev.ConsoleRenderer",
        },
    },
    "filters": {
        "require_debug_true": {"()": "django.utils.log.RequireDebugTrue"},
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "filters": ["require_debug_true"],
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "production_console": {
            "level": "WARNING",
            "filters": ["require_debug_false"],
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {
        "handlers": ["console", "production_console"],
        "level": env("LOG_LEVEL"),
    },
    "loggers": {
        "django": {
            "handlers": ["console", "production_console"],
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "production_console"],
            "level": env("LOG_LEVEL"),
            "propagate": False,
        },
        "celery": {
            "handlers": ["console", "production_console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
