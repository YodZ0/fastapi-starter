from fastapi import FastAPI, APIRouter

from src.api.v1 import router_v1
from src.settings import settings


def apply_routes(app: FastAPI) -> FastAPI:
    # Create main router
    router = APIRouter(prefix=settings.api.prefix)
    # Include API routers
    router.include_router(router_v1)
    # Include main router
    app.include_router(router)
    return app
