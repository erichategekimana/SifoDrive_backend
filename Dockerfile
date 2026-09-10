# =============================================================================
# Sifo Drive — Dockerfile
# Multi-stage build: development + production targets
# =============================================================================

# ---------------------------------------------------------------------------
# Base Stage: Shared Python base
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    pango1.0-tools \
    # WeasyPrint PDF dependencies
    libcairo2 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------------------------------------------------------------
# Development Stage
# ---------------------------------------------------------------------------
FROM base AS development

COPY requirements/development.txt requirements/development.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements/development.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------------------------------------------------------------------------
# Production Stage
# ---------------------------------------------------------------------------
FROM base AS production

# Create non-root user for security
RUN groupadd --gid 1001 sifo && \
    useradd --uid 1001 --gid sifo --shell /bin/bash --create-home sifo

COPY requirements/production.txt requirements/production.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements/production.txt

COPY --chown=sifo:sifo . .

# Collect static files
RUN python manage.py collectstatic --noinput --settings=config.settings.production 2>/dev/null || true

USER sifo

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "gthread", \
     "--threads", "2", \
     "--worker-tmp-dir", "/dev/shm", \
     "--timeout", "60", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
