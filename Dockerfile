# syntax=docker/dockerfile:1

# ============= #
# Stage 1: base #
# ============= #
FROM python:3.13-slim AS base

# uv is pinned, not `latest`, so the build stays reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Precompile installed packages: slower build, faster container start-up.
ENV UV_COMPILE_BYTECODE=1
# Docker layers span filesystems, where uv cannot hardlink out of its cache.
ENV UV_LINK_MODE=copy
# Use the interpreter already in this image instead of downloading a managed one.
ENV UV_PYTHON_DOWNLOADS=never
# The venv deliberately lives OUTSIDE /app: docker-compose.override.yml bind-mounts
# ./backend onto /app in dev, which would shadow an in-project .venv (and on a
# Windows host would hand a Scripts/-layout venv to this Linux container).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# Putting the venv on PATH keeps prestart.sh (`alembic`) and CMD (`uvicorn`)
# working verbatim - no `uv run`, no activation step.
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependency layer: manifests only, so editing source does not reinstall packages.
COPY pyproject.toml uv.lock ./

# ============ #
# Stage 2: dev #
# ============ #
FROM base AS dev

# --frozen: fail if uv.lock disagrees with pyproject.toml rather than silently re-resolving.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY . ./

CMD ["uvicorn", "src.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

# ============= #
# Stage 3: prod #
# ============= #
FROM base AS prod

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . ./

# Fallback bind address so the container starts even if RUN__HOST is not supplied
# via compose env (compose still overrides this when set).
ENV RUN__HOST=0.0.0.0

CMD uvicorn src.main:app --host "$RUN__HOST" --port "$RUN__PORT"
