# ── Ramus Cash Loans — Backend Dockerfile (Multi-stage) ──────────────────────
# Stage: base → development → production
# Production image is non-root, minimal, with no dev dependencies.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt


# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ── Production ────────────────────────────────────────────────────────────────
FROM base AS production

# Non-root user
RUN groupadd -r ramus && useradd -r -g ramus -s /sbin/nologin ramus

COPY --chown=ramus:ramus . .

USER ramus
EXPOSE 8000

# Gunicorn + uvicorn workers for production
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
