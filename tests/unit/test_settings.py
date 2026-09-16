"""
Tests for `src.settings`.

`Settings` is built fully explicitly in-process rather than parsed from `.env`,
so the assertions cannot drift with whatever the developer happens to have
configured locally - the same approach as `tests/unit/core/test_provider.py`.
"""

import pytest
from pydantic import SecretStr, ValidationError

from src.settings import (
    ApplicationConfig,
    DatabaseConfig,
    Environment,
    RedisConfig,
    RunConfig,
    Settings,
)


def make_redis_config(**overrides) -> RedisConfig:
    return RedisConfig(
        host="redis.invalid",
        port=6380,
        password=SecretStr("redis-p@ss"),
        db=9,
        **overrides,
    )


def make_settings(**overrides) -> Settings:
    fields = {
        "cors_origins": ["https://example.invalid"],
        "app": ApplicationConfig(title="test"),
        "run": RunConfig(host="127.0.0.1", port=8000, workers=1, reload=False),
        "db": DatabaseConfig(
            host="db.invalid",
            port=5433,
            user="tester",
            password=SecretStr("db-p@ss"),
            name="testdb",
        ),
        "redis": make_redis_config(),
    }
    return Settings(**{**fields, **overrides})


class TestCacheKeyPrefix:
    def test_joins_the_app_prefix_and_the_environment(self) -> None:
        """
        The trailing colon is part of the contract: `RedisCache._key()` appends
        the key straight onto this string and inserts no separator of its own.
        """
        settings = make_settings(
            environment=Environment.DEV,
            redis=make_redis_config(key_prefix="test"),
        )

        assert settings.cache_key_prefix == "test:dev:"

    def test_empty_app_prefix_leaves_no_leading_colon(self) -> None:
        settings = make_settings(
            environment=Environment.DEV,
            redis=make_redis_config(key_prefix=""),
        )

        assert settings.cache_key_prefix == "dev:"


class TestEnvironment:
    def test_rejects_an_unknown_environment(self) -> None:
        """
        The whole point of the enum: a typo in `.env` has to fail at startup
        instead of silently opening a cache namespace nothing else reads.
        """
        with pytest.raises(ValidationError):
            make_settings(environment="prodd")

    def test_defaults_to_dev(self) -> None:
        assert make_settings().environment is Environment.DEV


class TestDefaults:
    def test_redis_key_prefix(self) -> None:
        assert make_settings().redis.key_prefix == "app"
