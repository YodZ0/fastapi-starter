from unittest.mock import patch

import pytest
from pydantic import SecretStr

from src.core.cache.client import make_redis_client

HOST = "fakehost"
PORT = 6380
DB = 3

# What redis-py must be called with when only the required arguments are given.
# Asserted as one whole dict rather than field by field: that also catches an
# argument the factory stops passing altogether, and a failure shows the full
# diff instead of the first mismatch.
EXPECTED_MINIMAL_CALL = {
    "host": HOST,
    "port": PORT,
    "db": DB,
    "password": None,
    "max_connections": 20,
    "socket_timeout": 5.0,
    "socket_connect_timeout": 5.0,
    "socket_keepalive": True,
    "health_check_interval": 30,
    "decode_responses": True,
}

# The same call with every argument supplied. Each value differs from the
# default above, so an argument that gets dropped on the way through cannot
# coincide with what the default would have produced anyway. Note the three
# `_seconds` parameters: the factory renames them, so those are a translation
# rather than a pass-through.
EXPECTED_FULL_CALL = {
    "host": HOST,
    "port": PORT,
    "db": DB,
    "password": "p@ss",
    "max_connections": 7,
    "socket_timeout": 1.5,
    "socket_connect_timeout": 2.5,
    "socket_keepalive": False,
    "health_check_interval": 15,
    "decode_responses": False,
}


@pytest.fixture
def redis_cls():
    """
    Patched at the point of use, not at `redis.asyncio.Redis`: the factory holds
    its own reference to the imported name.
    """
    with patch("src.core.cache.client.Redis") as mock:
        yield mock


class TestMakeRedisClient:
    def test_returns_the_constructed_client(self, redis_cls) -> None:
        client = make_redis_client(host=HOST, port=PORT, db=DB)

        assert client is redis_cls.return_value

    def test_applies_defaults_for_omitted_arguments(self, redis_cls) -> None:
        make_redis_client(host=HOST, port=PORT, db=DB)

        redis_cls.assert_called_once()
        assert redis_cls.call_args.kwargs == EXPECTED_MINIMAL_CALL

    def test_forwards_every_argument(self, redis_cls) -> None:
        make_redis_client(
            host=HOST,
            port=PORT,
            db=DB,
            password=SecretStr("p@ss"),
            max_connections=7,
            socket_timeout_seconds=1.5,
            socket_connect_timeout_seconds=2.5,
            socket_keepalive=False,
            health_check_interval_seconds=15,
            decode_responses=False,
        )

        redis_cls.assert_called_once()
        assert redis_cls.call_args.kwargs == EXPECTED_FULL_CALL

    @pytest.mark.parametrize(
        ("password", "expected"),
        [
            (SecretStr("p@ss"), "p@ss"),
            # An empty secret is still a secret: it has to reach redis-py as ""
            # rather than collapse into None and silently drop authentication.
            (SecretStr(""), ""),
            (None, None),
        ],
        ids=("secret_is_unwrapped", "empty_secret_is_kept", "none_stays_none"),
    )
    def test_password(self, redis_cls, password, expected) -> None:
        make_redis_client(host=HOST, port=PORT, db=DB, password=password)

        assert redis_cls.call_args.kwargs["password"] == expected
