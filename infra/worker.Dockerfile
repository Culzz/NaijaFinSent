FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY naijafinsent ./naijafinsent
COPY services/api ./services/api

RUN pip install --no-cache-dir ".[api]"

WORKDIR /app/services/api

# One-shot per cron tick by default; switch to --loop via command override.
CMD ["python", "-m", "app.worker", "--once", "--limit", "100"]
