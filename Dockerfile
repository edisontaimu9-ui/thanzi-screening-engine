# Thanzi screening engine API (Phase 6). Stateless. Runtime dependencies only, no dev extras.
# Run behind Hope's gateway on a private network. No port is published by this image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    THANZI_MODELS_DIR=/app/models \
    PORT=8080

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[api]"
COPY models ./models

# Non-root. Secrets (THANZI_GATEWAY_KEY, THANZI_AUDIT_KEY) are supplied at run time, never baked in.
RUN useradd --system --uid 10001 --no-create-home thanzi
USER thanzi

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8080'), timeout=3)"]

CMD ["sh", "-c", "exec uvicorn --factory thanzi_screen.api.app:create_app_from_env --host 0.0.0.0 --port ${PORT} --no-server-header"]
