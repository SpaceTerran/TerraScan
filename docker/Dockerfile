FROM python:3.14-slim@sha256:9b81fe9acff79e61affb44aaf3b6ff234392e8ca477cb86c9f7fd11732ce9b6a

# -----------------------------------------------------------------------------
# Container Labels
# -----------------------------------------------------------------------------
# source:      Links to source code ("View Source" in registries)
# description: Shows in package listings
# licenses:    For compliance
#
# GITEA USERS: Update the source URL below to point to your Gitea repository
#   Example: https://git.yourdomain.com/your-org/TerraScan
#
LABEL org.opencontainers.image.source="https://github.com/SpaceTerran/TerraScan"
LABEL org.opencontainers.image.description="TerraScan - AI code review container for Gitea PRs"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/runner \
    PIP_NO_CACHE_DIR=1

# Security: run as non-root
RUN groupadd --gid 1000 reviewer \
    && useradd --uid 1000 --gid reviewer --shell /bin/bash --create-home reviewer

WORKDIR /app

COPY runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=reviewer:reviewer runner/ ./runner/
COPY --chown=reviewer:reviewer config/ ./config/

USER reviewer

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import yaml; print('ok')" || exit 1

ENTRYPOINT ["python", "/app/runner/main.py"]
