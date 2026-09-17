# FastAPI application boilerplate

## Setup

```sh
uv sync --frozen
cp .env.template .env
uv run --frozen pre-commit install
```

`.env` is git-ignored; `.env.template` is the tracked copy and lists every
setting with a comment on what it does and what it should become in production.
`src/settings.py` builds `Settings()` at import time and several of its fields
have no default, so **the application does not start without an `.env`** - that
is intentional, a missing database password should stop a deploy rather than be
guessed at.

The test suite is the exception: `tests/conftest.py` puts the mandatory fields
into the environment before `src` is imported, so `uv run --frozen pytest -m
"not integration"` passes on a fresh clone with no `.env` at all.

## Quality gates

`ruff check`, `ruff format`, `mypy` and `pytest` are one command, not four:

```sh
uv run --frozen pre-commit run --all-files
```

The hook list lives in [.pre-commit-config.yaml](.pre-commit-config.yaml) and is
the only definition of the gates - the command above and the git `pre-commit`
hook run that same list, so a local run and a blocked commit can never disagree.

### Tests

The suite is split by what it needs to run:

```sh
uv run --frozen pytest -m "not integration"  # no Docker; this is the commit gate
uv run --frozen pytest -m integration        # starts Postgres via testcontainers
uv run --frozen pytest --cov                 # both, with the coverage threshold
```

The `integration` marker is applied automatically to everything under
`tests/integration/`, so a new module there cannot silently end up in the
Docker-free selection. The HTTP-layer tests are Docker-free on purpose: they
drive the application through `httpx.ASGITransport`, which does not run the
ASGI lifespan, so no container, no Postgres and no Redis are involved.

Coverage is not in `addopts` - see the comment above `[tool.coverage.run]` in
[pyproject.toml](pyproject.toml) for why.

## Running it

```sh
docker compose up
```

`docker-compose.override.yaml` is picked up automatically and is the dev half:
it builds the `dev` stage, publishes the ports on `127.0.0.1`, mounts `src/`,
`tests/` and `alembic/` into the container, and adds RedisInsight on `:5540`.
Deploying is the same file list minus the override.

Set `DB__HOST=db` and `REDIS__HOST=redis` in `.env` before starting: the
defaults in the template point at `localhost`, which is correct for a local
`uvicorn` and wrong inside compose.

### Migrations

Schema changes are applied by a one-shot `migrate` service, not by the backend:

```
db (healthy) -> migrate (alembic upgrade head, exits 0) -> backend
```

`backend` waits on `service_completed_successfully`, so it never serves a
request against a schema that has not been upgraded. Running the upgrade from
the backend's entrypoint instead would fire it once per worker and once per
replica, all at the same time, against the same database.

`alembic/versions/` is empty in the template, so **today `migrate` is a no-op**:
it connects, finds nothing to apply and exits 0. That is the expected output,
not a broken service - it starts doing work with the first revision:

```sh
docker compose run --rm backend alembic revision --autogenerate -m "add users"
docker compose up          # migrate applies it before backend comes up
```

Note that the integration suite does *not* go through Alembic - it builds the
schema with `Base.metadata.create_all`, because its models are test fixtures
rather than part of the application schema.

## What this template deliberately does not include

- **Authentication and authorization.** No user model, no JWT, no session
  handling.
- **Rate limiting.**

Both are product decisions - which identity provider, which token lifetime,
which limits per which route - and a boilerplate that picks for you is one you
have to unpick first. What is here is the infrastructure underneath: database
access, cache, dependency injection, a generic CRUD repository, a typed error
hierarchy and their HTTP mapping.
