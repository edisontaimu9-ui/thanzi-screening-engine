# Thanzi screening engine API (Phases 6-7). Stateless. Runtime dependencies only, no dev extras.
# Dependency versions are pinned by constraints.txt. The base image is a floating tag: Dependabot watches it, and the
# deployer may pin it by digest (see docs/deployment/runbook.md).
# Run behind Hope's gateway on a private network. No port is published by this image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    THANZI_MODELS_DIR=/app/models \
    PORT=8080

# Apply the Debian security updates available at build time. The first CI Trivy scan found two HIGH findings in the
# base image's zlib1g that already had fixes (D104). Dependabot bumps of the base tag will also bring fixes.
RUN apt-get update \
 && apt-get -y --no-install-recommends upgrade \
 && rm -rf /var/lib/apt/lists/*

ARG VERSION=unknown
LABEL org.opencontainers.image.title="thanzi-screen" \
      org.opencontainers.image.description="Thanzi under-five malnutrition screening API. Release candidate, not validated. Decision support only." \
      org.opencontainers.image.version="${VERSION}"

WORKDIR /app
COPY pyproject.toml constraints.txt ./
COPY src ./src
RUN pip install -c constraints.txt ".[api]"
# Preterm screening lives in this image (POST /v1/screen), not in a second one. Fail the build if its JSON data did not
# reach the installed package. fenton2025_lms.json is CC BY-NC-ND 4.0 (Dr Tanis Fenton, 2025): shipped unmodified.
RUN python -c "import json, pathlib, thanzi_screen.preterm as p; d = pathlib.Path(p.__file__).parent; [json.loads((d / n).read_text()) for n in ('fenton2025_lms.json', 'preterm_rules.json', 'routing_config.json')]; assert 'CC BY-NC-ND 4.0' in json.loads((d / 'fenton2025_lms.json').read_text())['meta']['license']"
COPY models ./models

# Non-root. Secrets (THANZI_GATEWAY_KEY, THANZI_AUDIT_KEY) are supplied at run time, never baked in.
RUN useradd --system --uid 10001 --no-create-home thanzi
USER thanzi

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8080'), timeout=3)"]

CMD ["sh", "-c", "exec uvicorn --factory thanzi_screen.api.app:create_app_from_env --host 0.0.0.0 --port ${PORT} --no-server-header"]
