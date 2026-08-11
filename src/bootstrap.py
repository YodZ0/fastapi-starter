"""
Application bootstrap.
Creates app, applies: middleware, routes, handlers etc.
"""

import logging
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from src.di import setup_async_container
from src.logs import setup_logging
from src.middleware import apply_middleware
from src.router import apply_routes
from src.settings import settings

setup_logging(settings.base_dir)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started successfully!")
    yield
    await app.state.dishka_container.close()
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
    container = setup_async_container()
    setup_dishka(container, app)
    return app
