"""
Redis-backed application cache.
"""

from datetime import timedelta
from typing import cast

from redis.asyncio import Redis

# Applied by `set()` unless the caller says otherwise, so a forgotten TTL
# expires instead of turning into a key that lives forever.
DEFAULT_TTL_SECONDS = 300


class RedisCache:
    """
    Cache operations with async Redis client.

    Values are plain `str`: the client is built with `decode_responses=True`,
    and serialization (JSON or otherwise) belongs to the calling code. Nothing
    is decoded here, so the only kind of miss is a key that is not there.
    """

    def __init__(self, client: Redis, key_prefix: str = "") -> None:
        self._client = client
        self._key_prefix = key_prefix

    def _key(self, key: str) -> str:
        # The prefix already ends with its separator (see
        # `Settings.cache_key_prefix`), so nothing is inserted here.
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> str | None:
        # Assigned to an annotated local rather than returned directly: redis-py
        # types its commands as `ResponseT`, which is `Any`, and mypy's
        # `warn_return_any` rejects handing that straight back. Same below.
        #
        # The bytes branch is what decoding looks like as a runtime flag; the
        # client sets `decode_responses=True`, so it cannot happen here.
        value: bytes | str | None = await self._client.get(self._key(key))
        return cast(str | None, value)

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | timedelta | None = DEFAULT_TTL_SECONDS,
    ) -> None:
        # redis-py accepts both an int of seconds and a timedelta in `ex`, so
        # the caller's unit passes through untouched.
        await self._client.set(self._key(key), value, ex=ttl)

    async def delete(self, key: str) -> bool:
        # Redis answers with the number of keys removed; the caller only needs
        # to know whether the key was there, not the protocol it came from.
        deleted: int = await self._client.delete(self._key(key))
        return deleted > 0

    async def ping(self) -> bool:
        return await self._client.ping()
