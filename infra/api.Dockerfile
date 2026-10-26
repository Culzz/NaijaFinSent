FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; uvicorn serves sync workers fine here.
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY naijafinsent ./naijafinsent
COPY services/api ./services/api

RUN pip install --no-cache-dir ".[api]" && pip install --no-cache-dir alembic

WORKDIR /app/services/api

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD curl -sf http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
