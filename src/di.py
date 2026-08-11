"""
Dependency Injection (DI) container setup.
"""

from dishka import AsyncContainer, Provider, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from src.core.provider import CoreProvider


def setup_async_container(*extra_providers: Provider) -> AsyncContainer:
    """
    Creates async dependencies application container.

    `extra_providers` for test dependencies substitution (provider with `override=True`
    substitutes original).
    """
    return make_async_container(
        # Core providers
        FastapiProvider(),
        CoreProvider(),
        # Apps providers
        *extra_providers,
    )
