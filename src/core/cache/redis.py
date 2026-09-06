"""
Redis-backed application cache.
"""

from redis.asyncio import Redis


class RedisCache:
    """
    Cache operations with async Redis client.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def ping(self) -> bool:
        return await self._client.ping()
