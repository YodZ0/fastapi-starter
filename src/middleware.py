from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.settings import settings


def apply_middleware(app: FastAPI) -> FastAPI:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
