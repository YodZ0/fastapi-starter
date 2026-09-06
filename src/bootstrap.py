"""
Application bootstrap.
Creates app, applies: middleware, routes, handlers etc.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from src.core.cache.redis import RedisCache
from src.di import setup_async_container
from src.handlers import apply_exception_handlers
from src.logs import setup_logging
from src.middleware import apply_middleware
from src.router import apply_routes
from src.settings import settings

setup_logging(settings.base_dir)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: AsyncContainer = app.state.dishka_container

    try:
        cache = await container.get(RedisCache)
        await cache.ping()
    except Exception:
        # Starlette never runs the shutdown half of a lifespan whose startup
        # raised, so this is the only chance to release what the container has
        # already opened before the exception takes the process down.
        logger.exception("Cache is unreachable, application startup aborted.")
        await container.close()
        raise

    logger.info("Cache connection established.")
    logger.info("Application started successfully!")

    try:
        yield
    finally:
        # finally, not a bare statement after `yield`: a generator torn down by
        # GeneratorExit would otherwise skip the close and leak the pools.
        await container.close()
        logger.info("Application shut down.")


def create_app() -> FastAPI:
    """
    Creates and configure FastAPI application.

    Applies:
    1. Middlewares.
    2. Routes.
    3. Addition modules (admin-panel, handlers, etc.)
    """
    app = FastAPI(
        title=settings.app.title,
        lifespan=lifespan,
        docs_url=settings.app.docs_url,
        redoc_url=settings.app.redoc_url,
        openapi_url=settings.app.openapi_url,
    )
    app = apply_middleware(app)
    app = apply_routes(app)
    apply_exception_handlers(app)
    container = setup_async_container()
    setup_dishka(container, app)
    return app
