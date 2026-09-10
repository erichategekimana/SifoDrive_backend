# Sifo Drive — Backend API

Django REST Framework backend for the Sifo Drive digital driving academy platform.

## Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.1 + Django REST Framework |
| Database | PostgreSQL 16 (AES-256 encrypted PII columns) |
| Cache / Broker | Redis 7 |
| Async Tasks | Celery 5 + Celery Beat |
| Object Storage | MinIO (S3-compatible) |
| Auth | JWT (simplejwt) + Phone OTP |
| API Docs | drf-spectacular (Swagger + ReDoc) |
| PDF | WeasyPrint + ReportLab |
| Containerization | Docker + Docker Compose |

## Project Structure

```
SifoDrive_backend/
├── config/                     # Django project config
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   ├── development.py      # Dev overrides
│   │   └── production.py       # Production overrides
│   ├── urls.py                 # Master URL router (/api/v1/)
│   ├── celery.py               # Celery app configuration
│   ├── wsgi.py                 # Gunicorn entry point
│   └── asgi.py                 # Uvicorn entry point
│
├── apps/                       # All domain applications
│   ├── core/                   # Shared OOP bases
│   │   ├── models.py           # BaseModel, UUIDModel, SoftDeleteModel, etc.
│   │   ├── exceptions.py       # Typed exception hierarchy
│   │   ├── permissions.py      # Role-based DRF permissions
│   │   ├── pagination.py       # Standard response paginator
│   │   ├── mixins.py           # SuccessResponseMixin, SoftDeleteMixin
│   │   └── utils.py            # PIIEncryptor, OTP gen, phone utils
│   │
│   ├── accounts/               # User management & auth
│   ├── lms/                    # Learning Management System
│   ├── examinations/           # Exam engine + proctoring
│   ├── live_classes/           # Google Meet scheduling + attendance
│   ├── irembo/                 # Irembo booking concierge
│   ├── payments/               # MTN/Airtel MoMo integration
│   ├── notifications/          # SMS notifications (Celery tasks)
│   └── audit/                  # Immutable compliance audit logs
│
├── requirements/
│   ├── base.txt                # Shared dependencies
│   ├── development.txt         # Dev extras (debug toolbar, pytest)
│   └── production.txt          # Prod extras (gunicorn, sentry)
│
├── docker-compose.yml          # Local dev services
├── Dockerfile                  # Multi-stage build
├── manage.py
└── .env.example                # Environment variables template
```

## Quick Start (Local Development)

### 1. Set up environment

```bash
cp .env.example .env
# Edit .env with your local values
```

### 2. Start infrastructure (DB + Redis + MinIO)

```bash
docker compose up -d db redis minio
```

### 3. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
```

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Create a superuser

```bash
python manage.py createsuperuser
# Uses phone number as username
```

### 6. Start the development server

```bash
python manage.py runserver
```

### 7. (Optional) Start Celery worker

```bash
celery -A config worker --loglevel=info
```

## API Documentation

Once running, access:
- **Swagger UI**: http://localhost:8000/api/docs/swagger/
- **ReDoc**: http://localhost:8000/api/docs/redoc/
- **Django Admin**: http://localhost:8000/admin/

## Running Tests

```bash
pytest
```

## Architecture Principles

- **OOP First**: All domain models inherit from `BaseModel` (UUID PK + timestamps + soft delete).
- **Thin Views**: All business logic in `services.py`, views only handle HTTP serialization.
- **Typed Exceptions**: Every error condition has a specific exception class in `core/exceptions.py`.
- **Role-Based Access**: DRF permission classes in `core/permissions.py` enforce the 6-tier role system.
- **Compliance by Design**: National IDs stored AES-256 encrypted; audit logs are immutable.
- **Environment-Split Settings**: `base.py` → `development.py` / `production.py`.

## User Roles

| Role | Description |
|---|---|
| `STUDENT` | Enrolled learner with Student ID, pays tuition |
| `GUEST` | Free account, pay-per-exam |
| `TUTOR` | Course author, live class facilitator |
| `ENTERPRISE_ADMIN` | Driving school director (B2B lab accounts) |
| `BOARD_REVIEWER` | Reviews and certifies exam results |
| `SYSTEM_ADMIN` | Full platform access |