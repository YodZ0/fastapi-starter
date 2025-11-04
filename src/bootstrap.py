import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.settings import settings
from src.middleware import apply_middleware
from src.router import apply_routes
from src.logs import setup_logging

setup_logging(settings.base_dir)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started successfully!")
    yield
    logger.info("Application shut down.")


def create_app() -> FastAPI:
    """
    Creates and configure FastAPI application.

    Applies:
    1. Middlewares.
    2. Routes.
    3. Addition modules (admin-panel, handlers, etc.)
    """
    docs_url = "/docs" if settings.debug else None
    redoc_url = "/redoc" if settings.debug else None
    openapi_url = "/openapi.json" if settings.debug else None

    app = FastAPI(
        title="FastAPI app",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app = apply_middleware(app)
    app = apply_routes(app)
    return app
