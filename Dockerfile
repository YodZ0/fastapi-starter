# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.11.3

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ============= #
# Stage 1: base #
# ============= #
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# ============= #
# Stage 2: deps #
# ============= #
FROM base AS deps

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./

# ============== #
# Stage 3: build #
# ============== #
FROM deps AS builder

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --locked --no-dev --no-install-project

COPY .logging.yaml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN python -m compileall -q src

# ============ #
# Stage 4: dev #
# ============ #
FROM deps AS dev

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --locked

COPY . ./

CMD ["uvicorn", "src.main:app"]

# ============= #
# Stage 5: prod #
# ============= #
FROM base AS prod

RUN groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app --no-create-home app

 COPY --from=builder --chown=app:app /opt/venv /opt/venv
 COPY --from=builder --chown=app:app /app/.logging.yaml ./
 COPY --from=builder --chown=app:app /app/src ./src

USER app

CMD ["uvicorn", "src.main:app"]
