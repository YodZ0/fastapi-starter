from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.cache.redis import RedisCache


@pytest.fixture
def client():
    """
    `spec=Redis` so that renaming a method on the real client fails these tests
    instead of being silently auto-created on the mock.

    `ping` then has to be restored as an AsyncMock by hand: redis-py declares it
    as a plain `def` returning an awaitable, not as `async def`, so mock's
    autospec sees a sync function and builds a sync child - awaiting the result
    then fails with "object bool can't be used in 'await' expression".
    """
    client = AsyncMock(spec=Redis)
    client.ping = AsyncMock()
    return client


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

    async def test_construction_does_not_touch_the_client(self, client) -> None:
        """
        The cache is provided at APP scope, so building it must not open a
        connection - that has to stay lazy until the first call.
        """
        RedisCache(client)

        assert client.mock_calls == []
