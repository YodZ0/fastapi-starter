"""
Tests for the dishka wiring in `src.core.provider`.

Everything here goes through a real container rather than calling the provider
methods directly: `@provide` turns them into `CompositeDependencySource`, and
calling one by hand bypasses dishka entirely - which is to say it bypasses
scopes, graph resolution and generator cleanup, and those are the whole point
of the provider.

No Postgres and no Redis are involved. The two factories that would open a
socket are patched at the point of use, while `async_sessionmaker` and
`AsyncSession` stay real: a session bound to a mocked engine can be opened and
closed without ever connecting, because SQLAlchemy connects lazily on the first
query.

The fixtures below deliberately depend on nothing outside this module, so they
can be moved to a shared `tests/conftest.py` unchanged once `src/di.py` or
`src/bootstrap.py` need them too.
"""

from unittest.mock import AsyncMock, patch

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.entities.factory_type import FactoryType
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.cache.redis import RedisCache
from src.core.database.session_manager import SessionManager
from src.core.provider import CoreProvider
from src.settings import (
    ApplicationConfig,
    DatabaseConfig,
    Environment,
    RedisConfig,
    RunConfig,
    Settings,
)
from src.settings import settings as app_settings

EXPECTED_FACTORIES = {
    Settings: (Scope.APP, FactoryType.FACTORY),
    AsyncEngine: (Scope.APP, FactoryType.ASYNC_GENERATOR),
    async_sessionmaker[AsyncSession]: (Scope.APP, FactoryType.FACTORY),
    AsyncSession: (Scope.REQUEST, FactoryType.ASYNC_GENERATOR),
    SessionManager: (Scope.REQUEST, FactoryType.ASYNC_FACTORY),
    Redis: (Scope.APP, FactoryType.ASYNC_GENERATOR),
    RedisCache: (Scope.APP, FactoryType.FACTORY),
}

# Every value below differs from the default of the factory it ends up in, so
# an argument that gets dropped on the way through cannot coincide with what
# the default would have produced anyway.
DB_HOST = "db.invalid"
DB_PORT = 5433
DB_USER = "tester"
DB_PASSWORD = SecretStr("db-p@ss")
DB_NAME = "testdb"

REDIS_HOST = "redis.invalid"
REDIS_PORT = 6380
REDIS_PASSWORD = SecretStr("redis-p@ss")
REDIS_DB = 9
REDIS_KEY_PREFIX = "test-prefix"

ENVIRONMENT = Environment.STAGE

# What `Settings.cache_key_prefix` builds out of the two values above, and
# therefore what the provider has to hand to the cache.
EXPECTED_CACHE_KEY_PREFIX = "test-prefix:stage:"

# What `make_async_engine` must be called with, given the settings built below.
# The connection URL is passed positionally and asserted separately.
EXPECTED_ENGINE_CALL = {
    "echo": True,
    "echo_pool": True,
    "pool_size": 3,
    "max_overflow": 11,
    "pool_timeout": 1.5,
    "pool_recycle": 60,
    "pool_pre_ping": False,
    "statement_timeout_ms": 250,
}

# What `make_redis_client` must be called with. The password stays a SecretStr:
# unwrapping it is `make_redis_client`'s job (covered in test_client.py), so the
# provider doing it too would be a double unwrap.
EXPECTED_REDIS_CALL = {
    "host": REDIS_HOST,
    "port": REDIS_PORT,
    "db": REDIS_DB,
    "password": REDIS_PASSWORD,
    "max_connections": 4,
    "socket_timeout_seconds": 1.5,
    "socket_connect_timeout_seconds": 2.5,
    "health_check_interval_seconds": 15,
}


@pytest.fixture
def settings():
    """
    A fully explicit Settings, built in-process instead of parsed from `.env`,
    so the assertions below cannot drift with whatever the developer happens to
    have configured locally.
    """
    return Settings(
        environment=ENVIRONMENT,
        cors_origins=["https://example.invalid"],
        app=ApplicationConfig(title="test"),
        run=RunConfig(host="127.0.0.1", port=8000, workers=1, reload=False),
        db=DatabaseConfig(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            name=DB_NAME,
            echo=True,
            echo_pool=True,
            pool_size=3,
            max_overflow=11,
            pool_timeout=1.5,
            pool_recycle=60,
            pool_pre_ping=False,
            statement_timeout_ms=250,
        ),
        redis=RedisConfig(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            max_connections=4,
            socket_timeout_seconds=1.5,
            socket_connect_timeout_seconds=2.5,
            health_check_interval_seconds=15,
            key_prefix=REDIS_KEY_PREFIX,
        ),
    )


@pytest.fixture
def settings_override(settings: Settings):
    """
    `override=True` is how `setup_async_container` is documented to accept test
    doubles, so substituting the config uses the mechanism the application
    already ships rather than patching the module singleton.
    """

    class SettingsOverrideProvider(Provider):
        @provide(scope=Scope.APP, override=True)
        def get_settings(self) -> Settings:
            return settings

    return SettingsOverrideProvider()


@pytest.fixture
def make_engine():
    """
    Patched at the point of use, not at `src.core.database.session`: the
    provider holds its own reference to the imported name.
    """
    with patch("src.core.provider.make_async_engine") as mock:
        mock.return_value = AsyncMock(spec=AsyncEngine)
        yield mock


@pytest.fixture
def make_client():
    with patch("src.core.provider.make_redis_client") as mock:
        mock.return_value = AsyncMock(spec=Redis)
        yield mock


@pytest.fixture
async def container(settings_override, make_engine, make_client):
    """
    `FastapiProvider` is left out: `CoreProvider` does not depend on it, and
    pulling it in would require a request context this suite has no use for.

    Closing here is unconditional - dishka tolerates a second `close()`, so the
    cleanup tests can close the container themselves and still be torn down.
    """
    container = make_async_container(CoreProvider(), settings_override)
    yield container
    await container.close()


class TestCoreProviderWiring:
    def test_declares_every_dependency_with_the_expected_lifetime(self) -> None:
        factories = {
            factory.provides.type_hint: (factory.scope, factory.type)
            for factory in CoreProvider().factories
        }

        assert factories == EXPECTED_FACTORIES


class TestSettingsProvider:
    async def test_provides_the_module_singleton(self) -> None:
        """
        Not merely an equal Settings: a fresh one re-parses `.env` and leaves
        the container holding a config object that is not the one the rest of
        the code imports.

        Built without the override provider, since the identity of the real
        singleton is exactly what is under test.
        """
        container = make_async_container(CoreProvider())
        try:
            assert await container.get(Settings) is app_settings
        finally:
            await container.close()


class TestEngineConstruction:
    async def test_provides_the_constructed_engine(
        self,
        container: AsyncContainer,
        make_engine,
    ) -> None:
        engine = await container.get(AsyncEngine)

        assert engine is make_engine.return_value

    async def test_passes_the_connection_url_positionally(
        self,
        container: AsyncContainer,
        make_engine,
        settings,
    ) -> None:
        await container.get(AsyncEngine)

        assert make_engine.call_args.args == (settings.db.url,)

    async def test_forwards_every_database_setting(
        self,
        container: AsyncContainer,
        make_engine,
    ) -> None:
        await container.get(AsyncEngine)

        make_engine.assert_called_once()
        assert make_engine.call_args.kwargs == EXPECTED_ENGINE_CALL

    async def test_is_built_once_for_the_whole_application(
        self,
        container: AsyncContainer,
        make_engine,
    ) -> None:
        """
        The engine owns the connection pool, so a second instance would mean a
        second pool.
        """
        first = await container.get(AsyncEngine)
        second = await container.get(AsyncEngine)

        assert first is second
        make_engine.assert_called_once()

    async def test_session_factory_is_bound_to_the_engine(
        self,
        container: AsyncContainer,
    ) -> None:
        session_factory = await container.get(async_sessionmaker[AsyncSession])

        assert session_factory.kw["bind"] is await container.get(AsyncEngine)


class TestRedisClientConstruction:
    async def test_provides_the_constructed_client(
        self,
        container: AsyncContainer,
        make_client,
    ) -> None:
        client = await container.get(Redis)

        assert client is make_client.return_value

    async def test_forwards_every_redis_setting(
        self,
        container: AsyncContainer,
        make_client,
    ) -> None:
        await container.get(Redis)

        make_client.assert_called_once()
        assert make_client.call_args.kwargs == EXPECTED_REDIS_CALL

    async def test_is_built_once_for_the_whole_application(
        self,
        container: AsyncContainer,
        make_client,
    ) -> None:
        """
        The client owns the connection pool, so a second instance would mean a
        second pool.
        """
        first = await container.get(Redis)
        second = await container.get(Redis)

        assert first is second
        make_client.assert_called_once()

    async def test_cache_wraps_the_provided_client(
        self,
        container: AsyncContainer,
        make_client,
    ) -> None:
        cache = await container.get(RedisCache)

        assert isinstance(cache, RedisCache)
        assert cache._client is make_client.return_value

    async def test_cache_gets_the_assembled_key_prefix(
        self,
        container: AsyncContainer,
    ) -> None:
        """
        The cache takes a ready-made prefix, so the provider is the only place
        that can lose the environment part of it - and a cache writing under
        the wrong namespace fails silently.
        """
        cache = await container.get(RedisCache)

        assert cache._key_prefix == EXPECTED_CACHE_KEY_PREFIX

    async def test_building_the_cache_does_not_touch_the_client(
        self,
        container: AsyncContainer,
        make_client,
    ) -> None:
        """
        The cache is provided at APP scope, so resolving it must not open a
        connection - that has to stay lazy until the first call.
        """
        await container.get(RedisCache)

        assert make_client.return_value.mock_calls == []


class TestAppScopeCleanup:
    async def test_disposes_the_engine_and_closes_the_client_on_shutdown(
        self,
        container: AsyncContainer,
        make_engine,
        make_client,
    ) -> None:
        """
        Both hold a pool, so skipping teardown leaves connections open on the
        server after every restart until they time out.
        """
        await container.get(AsyncEngine)
        await container.get(Redis)

        await container.close()

        make_engine.return_value.dispose.assert_awaited_once()
        make_client.return_value.aclose.assert_awaited_once()

    async def test_survives_a_request_scope_without_releasing_anything(
        self,
        container: AsyncContainer,
        make_engine,
        make_client,
    ) -> None:
        """
        The pools outlive individual requests: leaving a request scope must not
        drag the APP-scoped resources down with it.
        """
        await container.get(AsyncEngine)
        await container.get(Redis)

        async with container(scope=Scope.REQUEST) as request_container:
            await request_container.get(SessionManager)

        make_engine.return_value.dispose.assert_not_awaited()
        make_client.return_value.aclose.assert_not_awaited()


class TestRequestScope:
    async def test_session_manager_wraps_the_request_session(
        self,
        container: AsyncContainer,
    ) -> None:
        """
        Repository and use case resolve `SessionManager` and `AsyncSession`
        separately within one request; if those were not the same session they
        would end up in different transactions, and nothing outside the
        container would show it.
        """
        async with container(scope=Scope.REQUEST) as request_container:
            manager = await request_container.get(SessionManager)
            session = await request_container.get(AsyncSession)

            assert manager._session is session

    async def test_each_request_gets_its_own_session_over_a_shared_engine(
        self,
        container: AsyncContainer,
    ) -> None:
        async with container(scope=Scope.REQUEST) as first_request:
            first_session = await first_request.get(AsyncSession)
            first_engine = await first_request.get(AsyncEngine)

        async with container(scope=Scope.REQUEST) as second_request:
            second_session = await second_request.get(AsyncSession)
            second_engine = await second_request.get(AsyncEngine)

        assert first_session is not second_session
        assert first_engine is second_engine

    async def test_session_is_closed_when_the_request_ends(
        self,
        container: AsyncContainer,
    ) -> None:
        """
        Spying rather than replacing, so the real `close()` still runs: an
        unclosed session would keep its connection checked out of the pool for
        the rest of the process.
        """
        with patch.object(
            AsyncSession, "close", autospec=True, side_effect=AsyncSession.close
        ) as close:
            async with container(scope=Scope.REQUEST) as request_container:
                session = await request_container.get(AsyncSession)

                close.assert_not_awaited()

        close.assert_awaited_once_with(session)
