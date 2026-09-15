"""
Tests for the container assembled in `src.di`.

Everything goes through a real container: `setup_async_container` is nothing
but a provider list, and the only way to tell whether a provider actually made
it in is to resolve something through the graph it produces.

No socket is opened. Of the dependencies below, `Settings` builds nothing,
`Request` comes from the request context, and `RedisCache` is always
overridden - `AsyncEngine` and `Redis` are deliberately never requested, so the
two factories that would construct a pool never run.
"""

from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, provide
from fastapi import Request

from src.core.cache.redis import RedisCache
from src.di import setup_async_container
from src.settings import Settings
from src.settings import settings as app_settings


class Marker:
    pass


# The minimum Starlette accepts for an http request. Nothing in it is read:
# dishka stores the object as a context value and hands the same one back.
REQUEST_SCOPE = {
    "type": "http",
    "method": "GET",
    "path": "/",
    "headers": [],
    "query_string": b"",
}


@pytest.fixture
def cache():
    return AsyncMock(spec=RedisCache)


class TestContainerComposition:
    async def test_provides_the_core_dependencies(self) -> None:
        """
        `Settings` rather than any other `CoreProvider` dependency: it is the
        one factory that constructs nothing, so resolving it proves the
        provider is wired in without opening a pool on the way.
        """
        container = setup_async_container()
        try:
            assert await container.get(Settings) is app_settings
        finally:
            await container.close()

    async def test_provides_the_fastapi_request_context(self) -> None:
        """
        `FastapiProvider` contributes context entries only, so it is invisible
        until a request scope is entered. Leaving it out breaks every route
        with a `FromDishka` dependency at request time rather than at startup,
        which is exactly the kind of failure a container should not defer.
        """
        request = Request(REQUEST_SCOPE)

        container = setup_async_container()
        try:
            async with container(
                context={Request: request},
                scope=Scope.REQUEST,
            ) as request_container:
                assert await request_container.get(Request) is request
        finally:
            await container.close()

    async def test_returns_a_new_container_for_each_call(self) -> None:
        """
        A module-level singleton would be shared by every app built in the
        process, so shutting one down would dispose the pools out from under
        the others - which is precisely what a test suite does.
        """
        first = setup_async_container()
        second = setup_async_container()

        try:
            assert first is not second
        finally:
            await first.close()
            await second.close()


class TestExtraProviders:
    async def test_an_overriding_provider_replaces_the_original(
        self,
        cache: RedisCache,
    ) -> None:
        """
        The substitution seam the public docstring promises, and the one every
        future suite will build its fixtures on.

        The override declares no `Redis` dependency, unlike the real factory,
        so a container that still reached the original would have had to
        construct a client to satisfy it. The identity assertion covers both:
        the double is returned, and nothing was built to return it.
        """

        class CacheOverrideProvider(Provider):
            @provide(scope=Scope.APP, override=True)
            def get_redis_cache(self) -> RedisCache:
                return cache

        container = setup_async_container(CacheOverrideProvider())
        try:
            assert await container.get(RedisCache) is cache
        finally:
            await container.close()

    async def test_an_extra_provider_adds_a_new_dependency(self) -> None:
        """
        An extra that overrides nothing must still reach the graph: this is how
        application providers get added alongside the core ones, and appending
        them to the wrong end of the list would silently drop them.
        """
        marker = Marker()

        class MarkerProvider(Provider):
            @provide(scope=Scope.APP)
            def get_marker(self) -> Marker:
                return marker

        container = setup_async_container(MarkerProvider())
        try:
            assert await container.get(Marker) is marker
        finally:
            await container.close()

    async def test_extra_providers_are_applied_after_the_core_ones(
        self,
        cache: RedisCache,
    ) -> None:
        """
        Position in the list is what makes overriding work at all: dishka keeps
        the last factory registered for a type, so an extra spliced in before
        `CoreProvider` would be the one discarded.

        `override=True` is deliberately absent here. The container is built
        with dishka's default validation, whose `implicit_override` check is
        off, so the flag documents the intent rather than enforcing it - which
        leaves this ordering as the only thing actually holding the seam up.
        """

        class CacheProvider(Provider):
            @provide(scope=Scope.APP)
            def get_redis_cache(self) -> RedisCache:
                return cache

        container = setup_async_container(CacheProvider())
        try:
            assert await container.get(RedisCache) is cache
        finally:
            await container.close()
