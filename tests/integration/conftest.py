"""
Fixtures for the integration suite.

The container, the engine and the schema are session-scoped, so Postgres is
started exactly once for the whole run. Isolation is per test instead, and it is
bought with a transaction rather than a fresh database:

    session scope   container -> engine -> create_all(Base.metadata)
    function scope  connection (BEGIN) -> session (SAVEPOINT) -> seed
                    -> TEST -> ROLLBACK

`SessionManager.get_session()` opens its own transaction whenever none is
running. Because the session is bound to a connection that already has one and
is configured with `join_transaction_mode="create_savepoint"`, each of those
`begin()` calls becomes a SAVEPOINT and each `commit()` a RELEASE SAVEPOINT.
The outer `rollback()` at the end of the test undoes all of it at once, so no
test can see - or be broken by - what another test wrote.

Nothing below knows about `CRUDRepository`: the ladder ends at `session` and
`session_manager`, which is all any repository under test needs.
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.config import testcontainers_config

from src.core.database.base_model import Base
from src.core.database.session import make_async_engine
from src.core.database.session_manager import SessionManager

from .models import Car, Gadget, Truck, Vehicle, Widget

POSTGRES_IMAGE = "postgres:18.6-alpine"

# Ryuk is testcontainers' own watchdog container: it reaps anything left behind
# if the test process dies without unwinding. It is turned off because
# testcontainers 4.15 reads Ryuk's published port as soon as the container
# reports "running", and Docker Desktop only publishes the NAT mapping a moment
# later - on Windows and macOS that race loses every time, and the whole suite
# errors out before Postgres is even pulled.
#
# Losing it costs little here: `postgres_container` is a `with` block, so the
# normal path - pass, fail or KeyboardInterrupt - still stops the container. Only
# a hard kill of the interpreter can now strand one.
testcontainers_config.ryuk_disabled = True

_PACKAGE_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Mark everything in this package as `integration`.

    Applied automatically rather than by hand so that a new module cannot
    silently end up in the default (Docker-free) selection.
    """
    for item in items:
        if item.path is not None and _PACKAGE_ROOT in item.path.parents:
            item.add_marker(pytest.mark.integration)


# --- SESSION SCOPE ---


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """
    Start one throwaway Postgres for the whole run.

    Synchronous on purpose - the container is plain blocking IO, and keeping it
    out of the event loop means the readiness probe cannot interfere with it.
    `driver=None` keeps a sync DBAPI out of the connection URL; the stack here
    is asyncpg only.
    """
    with PostgresContainer(POSTGRES_IMAGE, driver=None) as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> URL:
    """
    Build the asyncpg URL the same way `DatabaseConfig.url` does.
    """
    return URL.create(
        drivername="postgresql+asyncpg",
        username=postgres_container.username,
        password=postgres_container.password,
        host=postgres_container.get_container_host_ip(),
        port=int(postgres_container.get_exposed_port(postgres_container.port)),
        database=postgres_container.dbname,
    )


@pytest.fixture(scope="session")
async def engine(database_url: URL) -> AsyncIterator[AsyncEngine]:
    """
    The production engine factory, pointed at the container.
    """
    engine = make_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
async def _create_schema(engine: AsyncEngine) -> None:
    """
    Create the tables once.

    `create_all`, not `alembic upgrade head`: the project has no revisions yet,
    and the test models are not part of the application schema anyway.
    Importing `.models` above is what fills `Base.metadata` here.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


# --- FUNCTION SCOPE ---


@pytest.fixture
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """
    A connection with an open transaction that is always rolled back.

    This is the outer half of the isolation: everything a test writes lives
    inside this transaction and dies with it.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest.fixture
async def session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """
    A session bound to that connection, turning its own transactions into
    savepoints.

    `make_async_session_factory` is deliberately not reused: it binds to an
    `AsyncEngine`, and this scheme needs the session on the very
    `AsyncConnection` that holds the outer transaction. The two settings it
    would have supplied are repeated here so the session still behaves exactly
    like a production one.
    """
    async with AsyncSession(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as session:
        yield session


@pytest.fixture
def session_manager(session: AsyncSession) -> SessionManager:
    return SessionManager(session)


# --- DATA ---


@dataclass(frozen=True)
class SeedData:
    """
    The rows every test starts from.

    Holds detached ORM instances: IDs are read off them rather than hardcoded,
    because `BaseInt.id` is `GENERATED ALWAYS` and the database alone decides
    what it is.
    """

    widgets: list[Widget]
    gadgets: list[Gadget]
    vehicles: list[Vehicle]
    cars: list[Car]
    trucks: list[Truck]


@pytest.fixture
async def seed(session: AsyncSession) -> SeedData:
    """
    Insert a fixed set of rows inside the test's savepoint.

    The insert is committed so that the session ends up with no transaction
    open: `SessionManager.get_session()` then starts one - a savepoint - per
    repository call, which is what the code does in production. The commit only
    releases that savepoint; the outer transaction still rolls everything back.

    The instances are expunged afterwards so that the identity map is empty when
    the test begins, and a repository read cannot be served a cached object
    instead of the row it just asked for.
    """
    widgets = [
        Widget(name="Alpha widget", slug="alpha", weight=10, description="first"),
        Widget(name="Beta widget", slug="beta", weight=20, description="second"),
        Widget(name="Gamma widget", slug="gamma", weight=30, description=None),
    ]
    gadgets = [
        Gadget(name="Alpha gadget", code="A-1"),
        Gadget(name="Beta gadget", code="B-2"),
    ]
    vehicles = [Vehicle(name="Bare vehicle", kind="vehicle")]
    cars = [Car(name="Sedan", doors=4), Car(name="Coupe", doors=2)]
    trucks = [Truck(name="Hauler", payload_kg=8000)]

    session.add_all([*widgets, *gadgets, *vehicles, *cars, *trucks])
    await session.flush()
    await session.commit()
    session.expunge_all()

    return SeedData(
        widgets=widgets,
        gadgets=gadgets,
        vehicles=vehicles,
        cars=cars,
        trucks=trucks,
    )
