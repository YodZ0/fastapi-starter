from datetime import timedelta
from unittest.mock import AsyncMock, call

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.cache.redis import DEFAULT_TTL_SECONDS, RedisCache

KEY_PREFIX = "fs:dev:"


@pytest.fixture
def client():
    """
    `spec=Redis` so that renaming a method on the real client fails these tests
    instead of being silently auto-created on the mock.

    Every command then has to be restored as an AsyncMock by hand: redis-py
    declares them as plain `def`s returning an awaitable, not as `async def`, so
    mock's autospec sees sync functions and builds sync children - awaiting the
    result then fails with "object bool can't be used in 'await' expression".
    """
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock()
    client.get = AsyncMock()
    client.set = AsyncMock()
    # `delete` answers with a count that the cache compares against 0, so it
    # needs a real int even where the test does not care about the result.
    client.delete = AsyncMock(return_value=0)
    return client


@pytest.fixture
def cache(client):
    """
    Built with a non-empty prefix so that every test below also covers the key
    being prefixed, rather than leaving that to one dedicated case.
    """
    return RedisCache(client, key_prefix=KEY_PREFIX)


class TestGet:
    async def test_delegates_to_client_with_the_prefixed_key(
        self, cache: RedisCache, client
    ) -> None:
        client.get.return_value = "value"

        result = await cache.get("user:42")

        assert result == "value"
        client.get.assert_awaited_once_with("fs:dev:user:42")

    async def test_returns_none_on_a_miss(self, cache: RedisCache, client) -> None:
        """
        Nothing is deserialized here, so an absent key is the only kind of miss
        there is - it must surface as None rather than as an error.
        """
        client.get.return_value = None

        assert await cache.get("missing") is None


class TestSet:
    async def test_applies_the_default_ttl(self, cache: RedisCache, client) -> None:
        """
        Pins the default: a caller who forgets the TTL must not end up with a
        key that never expires.
        """
        await cache.set("user:42", "value")

        assert client.set.await_args.kwargs["ex"] == DEFAULT_TTL_SECONDS == 300

    async def test_passes_the_prefixed_key_and_the_value_unchanged(
        self, cache: RedisCache, client
    ) -> None:
        await cache.set("user:42", "value")

        assert client.set.await_args.args == ("fs:dev:user:42", "value")

    async def test_forwards_an_explicit_ttl_in_seconds(
        self, cache: RedisCache, client
    ) -> None:
        await cache.set("user:42", "value", ttl=60)

        assert client.set.await_args.kwargs["ex"] == 60

    async def test_forwards_a_timedelta_ttl_as_is(
        self, cache: RedisCache, client
    ) -> None:
        """
        redis-py accepts a timedelta in `ex` itself, so converting it here would
        only be a chance to get the unit wrong.
        """
        ttl = timedelta(minutes=5)

        await cache.set("user:42", "value", ttl=ttl)

        assert client.set.await_args.kwargs["ex"] is ttl

    async def test_stores_without_expiry_when_ttl_is_none(
        self, cache: RedisCache, client
    ) -> None:
        await cache.set("user:42", "value", ttl=None)

        assert client.set.await_args.kwargs["ex"] is None


class TestDelete:
    async def test_deletes_the_prefixed_key(self, cache: RedisCache, client) -> None:
        client.delete.return_value = 1

        await cache.delete("user:42")

        client.delete.assert_awaited_once_with("fs:dev:user:42")

    async def test_reports_a_removed_key(self, cache: RedisCache, client) -> None:
        client.delete.return_value = 1

        assert await cache.delete("user:42") is True

    async def test_reports_a_key_that_was_not_there(
        self, cache: RedisCache, client
    ) -> None:
        """
        Redis answers with a count; the caller gets the fact of the deletion, so
        that it never has to know about that part of the protocol.
        """
        client.delete.return_value = 0

        assert await cache.delete("user:42") is False


class TestKeyPrefix:
    @pytest.mark.parametrize(
        ("command", "operation", "expected_call"),
        [
            ("get", lambda cache: cache.get("user:42"), call("user:42")),
            (
                "set",
                lambda cache: cache.set("user:42", "value"),
                call("user:42", "value", ex=DEFAULT_TTL_SECONDS),
            ),
            ("delete", lambda cache: cache.delete("user:42"), call("user:42")),
        ],
        ids=["get", "set", "delete"],
    )
    async def test_empty_prefix_leaves_the_key_untouched(
        self, client, command, operation, expected_call
    ) -> None:
        """
        The constructor default keeps the cache usable without settings, and
        every method has to route through `_key()` for that to hold.
        """
        await operation(RedisCache(client))

        assert getattr(client, command).await_args == expected_call


class TestRedisCache:
    async def test_ping_delegates_to_client(self, client) -> None:
        client.ping.return_value = True

        result = await RedisCache(client).ping()

        assert result is True
        client.ping.assert_awaited_once()

    async def test_ping_propagates_connection_error(self, client) -> None:
        """
        `ping()` is annotated `-> bool`, but redis-py raises on an unreachable
        server rather than returning False. Pinned here so that a health check
        built on top of it is written against the actual contract.
        """
        client.ping.side_effect = RedisConnectionError("unreachable")

        with pytest.raises(RedisConnectionError, match="unreachable"):
            await RedisCache(client).ping()

    @pytest.mark.parametrize(
        ("command", "operation"),
        [
            ("get", lambda cache: cache.get("user:42")),
            ("set", lambda cache: cache.set("user:42", "value")),
            ("delete", lambda cache: cache.delete("user:42")),
        ],
        ids=["get", "set", "delete"],
    )
    async def test_propagates_connection_error(
        self, cache: RedisCache, client, command, operation
    ) -> None:
        """
        Infrastructure failures are not swallowed into a miss: a caller told the
        key is absent would happily overwrite whatever Redis still holds.
        """
        getattr(client, command).side_effect = RedisConnectionError("unreachable")

        with pytest.raises(RedisConnectionError, match="unreachable"):
            await operation(cache)

    async def test_construction_does_not_touch_the_client(self, client) -> None:
        """
        The cache is provided at APP scope, so building it must not open a
        connection - that has to stay lazy until the first call.
        """
        RedisCache(client)

        assert client.mock_calls == []
