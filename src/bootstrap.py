from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.router import apply_routes
from src.middleware import apply_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(">>> Start src")
    yield
    print("<<< Dispose src")


def create_app() -> FastAPI:
    app = FastAPI(
        title="FastAPI",
        description="Application escription",
        lifespan=lifespan,
    )
    app = apply_routes(apply_middleware(app))
    return app
