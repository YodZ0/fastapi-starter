"""
Test environment for the whole suite.

`src/settings.py` instantiates `Settings()` at import time, and the fields
below have no defaults - so on a clone without a `.env` the *collection* of
every module that imports `src` fails, not just one test. pytest imports this
file before any test module, which is early enough to hand those fields over
through the environment.

Two deliberate choices:

- `setdefault`, not assignment: a value already present in the environment - a
  CI job, or a developer debugging against a real service - is kept.
- Only the fields that have no default are listed. Everything else comes from
  `Settings`, so this file does not have to track new optional settings.

Because pydantic-settings ranks environment variables above `.env`, these
values also win over whatever the developer happens to have configured
locally, which is what keeps the unit suite deterministic. Nothing here talks
to Postgres or Redis: the hosts are unroutable on purpose, and the tests that
need a real server (`tests/integration/`) get their own from testcontainers.
"""

import os

# --- Settings ---
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')

# --- Application ---
os.environ.setdefault("APP__TITLE", "FastAPI Starter (test)")

# --- Run ---
os.environ.setdefault("RUN__HOST", "127.0.0.1")
os.environ.setdefault("RUN__PORT", "8000")
os.environ.setdefault("RUN__WORKERS", "1")
os.environ.setdefault("RUN__RELOAD", "false")

# --- Database ---
os.environ.setdefault("DB__HOST", "db.invalid")
os.environ.setdefault("DB__PORT", "5432")
os.environ.setdefault("DB__USER", "test")
os.environ.setdefault("DB__PASSWORD", "test")
os.environ.setdefault("DB__NAME", "test")

# --- Cache ---
os.environ.setdefault("REDIS__HOST", "redis.invalid")
os.environ.setdefault("REDIS__PORT", "6379")
os.environ.setdefault("REDIS__PASSWORD", "test")
os.environ.setdefault("REDIS__DB", "0")
