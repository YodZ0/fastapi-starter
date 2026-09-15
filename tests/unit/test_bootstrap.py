"""
Tests for `src.bootstrap`.

`lifespan` runs against an `AsyncMock(spec=AsyncContainer)` rather than a real
container: every assertion here is about whether `close()` is awaited and how
often, and on a real container that is observable only through whichever
resources it happens to be holding at the time.

Importing this module imports `src.bootstrap`, which calls `setup_logging()` at
import time - so `.logging.yaml` has to exist for collection to succeed.
`src.main` is deliberately never imported: it calls `create_app()` at import
time, and nothing here needs a second application.
"""

from unittest.mock import AsyncMock, patch

import pytest
from dishka import AsyncContainer
from fastapi import FastAPI
from redis.exceptions import ConnectionError as RedisConnectionError

from src.bootstrap import create_app, lifespan
from src.core.cache.redis import RedisCache
from src.settings import settings


@pytest.fixture
def cache():
    """
    `RedisCache.ping` is a real `async def`, so `spec` yields a working
    AsyncMock child - no need for the redis-py workaround in test_redis.py,
    where `ping` is declared as a plain function returning an awaitable.
    """
    return AsyncMock(spec=RedisCache)


@pytest.fixture
def container(cache):
    """
    A double rather than a real container: the assertions below are about when
    `close()` is awaited and how many times, which a real container exposes
    only indirectly, through whatever it happens to have opened.
    """
    container = AsyncMock(spec=AsyncContainer)
    container.get.return_value = cache
    return container


@pytest.fixture
def app(container):
    app = FastAPI()
    app.state.dishka_container = container
    return app


@pytest.fixture
async def created_app():
    """
    The real `create_app()`. It opens nothing - SQLAlchemy and redis-py both
    connect lazily and no dependency is resolved here - but it does build a
    container, closed on teardown rather than left to the garbage collector.
    """
    created_app = create_app()
    yield created_app
    await created_app.state.dishka_container.close()


class TestLifespanStartup:
    async def test_pings_the_cache_resolved_from_the_app_state(
        self,
        app: FastAPI,
        container,
        cache,
    ) -> None:
        async with lifespan(app):
            pass

        container.get.assert_awaited_once_with(RedisCache)
        cache.ping.assert_awaited_once()

    async def test_keeps_the_container_open_while_the_application_runs(
        self,
        app: FastAPI,
        container,
    ) -> None:
        """
        The whole point of an APP-scoped container: closing it once startup
        succeeded would dispose the pools before the first request arrives.
        """
        async with lifespan(app):
            container.close.assert_not_awaited()

    async def test_a_falsy_ping_does_not_abort_startup(
        self,
        app: FastAPI,
        cache,
        container,
    ) -> None:
        """
        The return value of `ping()` is ignored on purpose: redis-py raises on
        an unreachable server instead of returning False - pinned by
        `test_ping_propagates_connection_error` in test_redis.py - so the
        exception is the only failure signal there is to act on.
        """
        cache.ping.return_value = False

        async with lifespan(app):
            container.close.assert_not_awaited()


class TestLifespanStartupFailure:
    """
    Starlette never runs the shutdown half of a lifespan whose startup raised,
    so the close inside the `except` is the only chance to release whatever the
    container already opened. Each test asserts it happens exactly once: a
    second close would mean the `finally` ran as well.
    """

    async def test_closes_the_container_when_the_ping_fails(
        self,
        app: FastAPI,
        cache,
        container,
    ) -> None:
        cache.ping.side_effect = RedisConnectionError("unreachable")

        with pytest.raises(RedisConnectionError, match="unreachable"):
            async with lifespan(app):
                pass

        container.close.assert_awaited_once()

    async def test_closes_the_container_when_resolving_the_cache_fails(
        self,
        app: FastAPI,
        container,
    ) -> None:
        """
        The handler catches `Exception`, not just connection errors: a
        misconfigured provider blows up inside `container.get` before the ping
        is ever reached, and it strands the same pools.
        """
        container.get.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(app):
                pass

        container.close.assert_awaited_once()

    async def test_logs_the_failure_before_aborting(self, app: FastAPI, cache) -> None:
        """
        The only operator-visible sign that the process died on purpose, and
        `logger.exception` rather than `logger.error` so the traceback survives.

        Patched instead of captured with `caplog`: `.logging.yaml` sets
        `propagate: false` on the `src` logger, so its records never reach the
        root handler pytest installs.
        """
        cache.ping.side_effect = RedisConnectionError("unreachable")

        with (
            patch("src.bootstrap.logger") as logger,
            pytest.raises(RedisConnectionError, match="unreachable"),
        ):
            async with lifespan(app):
                pass

        logger.exception.assert_called_once()


class TestLifespanShutdown:
    async def test_closes_the_container_on_a_clean_shutdown(
        self,
        app: FastAPI,
        container,
    ) -> None:
        async with lifespan(app):
            pass

        container.close.assert_awaited_once()

    async def test_closes_the_container_when_the_application_body_raises(
        self,
        app: FastAPI,
        container,
    ) -> None:
        """
        An exception thrown back into the lifespan - a later ASGI layer failing
        its own startup, for instance - must not take the pools down with it.
        """
        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(app):
                raise RuntimeError("boom")

        container.close.assert_awaited_once()

    async def test_closes_the_container_when_the_lifespan_is_torn_down(
        self,
        app: FastAPI,
        container,
    ) -> None:
        """
        Why the close sits in a `finally` and not in a bare statement after the
        `yield`: a generator discarded without its shutdown being driven gets a
        `GeneratorExit` thrown in at the `yield`, and only a `finally` runs
        after that.

        `__wrapped__` is the undecorated generator function - the context
        manager `asynccontextmanager` returns offers no way to reach `aclose()`.
        """
        generator = lifespan.__wrapped__(app)  # type: ignore[attr-defined]
        await anext(generator)

        await generator.aclose()

        container.close.assert_awaited_once()


class TestCreateApp:
    async def test_configures_the_app_from_settings(self, created_app: FastAPI) -> None:
        """
        The documentation endpoints are switched off per environment through
        the settings, so hardcoding any of them would publish the schema of a
        deployment that asked for it to stay hidden.
        """
        assert created_app.title == settings.app.title
        assert created_app.docs_url == settings.app.docs_url
        assert created_app.redoc_url == settings.app.redoc_url
        assert created_app.openapi_url == settings.app.openapi_url

    async def test_installs_the_application_lifespan(self, container, cache) -> None:
        """
        Identity is not assertable: `include_router` merges the application
        lifespan with the sub-router's default one, so the router ends up
        holding a wrapper rather than `lifespan` itself. Driving that wrapper
        is the stronger check anyway - it shows the installed context is the
        one that checks the cache and releases the container, which is all the
        app would lose if the argument were dropped.

        The container is substituted so entering the lifespan pings a double
        rather than a Redis server that is not running.
        """
        with patch("src.bootstrap.setup_async_container", return_value=container):
            app = create_app()

        async with app.router.lifespan_context(app):
            container.close.assert_not_awaited()

        container.get.assert_awaited_once_with(RedisCache)
        cache.ping.assert_awaited_once()
        container.close.assert_awaited_once()

    async def test_attaches_the_container_to_the_app_state(
        self,
        created_app: FastAPI,
    ) -> None:
        """
        `app.state.dishka_container` is the exact attribute `lifespan` reads,
        which makes it the seam between the two functions in this module.
        """
        assert isinstance(created_app.state.dishka_container, AsyncContainer)

    async def test_each_app_gets_its_own_container(self) -> None:
        """
        A container shared between applications would be closed by the first
        shutdown, leaving the second serving requests over disposed pools.
        """
        first = create_app()
        second = create_app()

        try:
            assert first.state.dishka_container is not second.state.dishka_container
        finally:
            await first.state.dishka_container.close()
            await second.state.dishka_container.close()


class TestCreateAppPipeline:
    def test_threads_the_app_through_every_setup_step(self) -> None:
        """
        `apply_middleware` and `apply_routes` return the application instead of
        mutating in place, so a step that drops the returned value silently
        discards everything the previous one added. Only following the value
        from one call to the next catches that; asserting that each step merely
        ran would not.

        Patched at the point of use: `src.bootstrap` holds its own references
        to the imported names.
        """
        with (
            patch("src.bootstrap.apply_middleware") as apply_middleware,
            patch("src.bootstrap.apply_routes") as apply_routes,
            patch("src.bootstrap.apply_exception_handlers") as apply_handlers,
            patch("src.bootstrap.setup_async_container") as setup_container,
            patch("src.bootstrap.setup_dishka") as setup_dishka,
        ):
            app = create_app()

        assert isinstance(apply_middleware.call_args.args[0], FastAPI)
        apply_routes.assert_called_once_with(apply_middleware.return_value)
        apply_handlers.assert_called_once_with(apply_routes.return_value)
        setup_dishka.assert_called_once_with(
            setup_container.return_value, apply_routes.return_value
        )
        assert app is apply_routes.return_value
