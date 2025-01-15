from fastapi import FastAPI
from src.apps.healthcheck.router import router as healthcheck_router


def apply_routes(app: FastAPI) -> FastAPI:
    app.include_router(healthcheck_router)
    return app
