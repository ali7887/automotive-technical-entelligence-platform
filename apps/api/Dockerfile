# Production image for the ATIP API.
#   docker build -t atip-api apps/api
#   docker run --rm -p 8000:8000 --env-file .env atip-api
# Migrations are NOT run at container start (see docs/12_RELEASE_RUNBOOK.md):
#   docker run --rm --env-file .env atip-api alembic upgrade head

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# dependency layer first so code edits don't re-resolve the lock
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN groupadd --system atip && useradd --system --gid atip atip \
    && mkdir -p /data/uploads && chown atip:atip /data/uploads
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
# alembic tree ships alongside the venv so the image can run its own migrations
COPY alembic.ini ./
COPY alembic ./alembic
ENV PATH="/app/.venv/bin:$PATH" \
    ENVIRONMENT=production \
    STORAGE_DIR=/data/uploads
USER atip
EXPOSE 8000
# liveness only: dependency outages must not kill the container
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"]
CMD ["uvicorn", "atip_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
