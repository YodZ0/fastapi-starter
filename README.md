# FastAPI application boilerplate

An async FastAPI template with the infrastructure already wired: SQLAlchemy 2
over asyncpg, Alembic, Redis, dishka for dependency injection,
pydantic-settings for configuration, Typer for management commands. Python
3.13, dependencies managed with `uv`, Postgres-only by design.

It is a starting point for a layered application, not a framework: there is one
prescribed way to add a feature, and it is [documented](docs/domain.md) rather
than enforced.

## What's inside

```text
src/
├── main.py              # ASGI entrypoint and the uvicorn runner
├── bootstrap.py         # create_app(), lifespan
├── di.py                # the dishka container
├── router.py            # /api prefix
├── api/v1.py            # /v1 prefix; domain routers are included here
├── middleware.py        # CORS, request id, process time
├── settings.py          # Settings(), the module-level singleton
├── logs.py              # dictConfig loader and the request-id log filter
├── handlers/            # exception -> HTTP status mapping
├── apps/                # one package per domain
│   └── healthz/
├── cli/                 # Typer commands
└── core/
    ├── context.py       # request-id ContextVar
    ├── depends.py       # shared FastAPI dependencies (Pagination)
    ├── provider.py      # CoreProvider: settings, engine, session, cache
    ├── enums.py
    ├── type_vars.py
    ├── cache/           # Redis client factory and a small cache wrapper
    ├── database/        # Base models, mixins, engine, SessionManager
    ├── exceptions/      # BusinessLogicException and repository errors
    ├── repositories/    # CRUDRepository
    └── schemas/         # base schemas, pagination, error bodies
```

- **A layered domain structure.** Model, schema, repository, service, use case,
  router - with the rule that no ORM instance ever leaves the repository.
- **A generic async CRUD repository.** Pagination with total counts, ILIKE
  search, sorting, bulk writes, Postgres upsert and joined-table inheritance,
  all from declaring four generic arguments.
- **Dependency injection** with two scopes, pool owners at application scope and
  per-request sessions, plus a test-override seam.
- **A typed business-error hierarchy** mapped to HTTP statuses in one place.
- **Request ids** taken from `X-Request-ID` or generated, propagated through a
  `ContextVar` into every log line.
- **Configuration that fails loudly** - mandatory settings have no defaults.
- **A Typer CLI**, including a renderer for the dependency graph.
- **Docker Compose** with a one-shot `migrate` service gated ahead of the
  backend.
- **One command for every quality gate**, shared by the local run and the git
  hook.

Not included, deliberately: authentication and rate limiting. See the
[last section](#what-this-template-deliberately-does-not-include).

## Documentation

| Page | Covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Layers, app assembly, routing, middleware, request context, error mapping, settings |
| [docs/domain.md](docs/domain.md) | What a domain contains, file by file, and the five places it is connected to the application |
| [docs/repository.md](docs/repository.md) | `CRUDRepository`: every method, search and sorting, joined-table inheritance, transactions |
| [docs/schemas.md](docs/schemas.md) | The Read/Create/Update triad, pagination, camelCase API schemas, error bodies |
| [docs/di.md](docs/di.md) | dishka scopes, writing a provider, overriding dependencies in tests, use outside a request |
| [docs/cli.md](docs/cli.md) | Adding commands and command groups, async commands, resolving dependencies in one |

Start with [docs/domain.md](docs/domain.md) - adding a feature is the first
thing anyone does here.

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
docker compose up -d --build
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

```text
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
docker compose up -d --build      # migrate applies it before backend comes up
```

Note that the integration suite does _not_ go through Alembic - it builds the
schema with `Base.metadata.create_all`, because its models are test fixtures
rather than part of the application schema.

## CLI

```sh
uv run --frozen python -m src.cli --help
uv run --frozen python -m src.cli sys check    # smoke-test the entrypoint
uv run --frozen python -m src.cli di graph     # render the dependency graph
```

There is no console script because `[tool.uv] package = false` - see
[docs/cli.md](docs/cli.md), which also covers adding commands, async commands
and resolving application dependencies inside one.

## What this template deliberately does not include

- **Authentication and authorization.** No user model, no JWT, no session
  handling.
- **Rate limiting.**

Both are product decisions - which identity provider, which token lifetime,
which limits per which route - and a boilerplate that picks for you is one you
have to unpick first. What is here is the infrastructure underneath: database
access, cache, dependency injection, a generic CRUD repository, a typed error
hierarchy and their HTTP mapping.
