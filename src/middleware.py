import time
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.settings import settings


async def calc_process_time(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    Calculate process time middleware
    """
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.5f}"
    return response


def apply_middleware(app: FastAPI) -> FastAPI:
    """
    Applies middlewares to FastAPI application.
    Notice: Last added middleware will be called first.
    """
    app.add_middleware(BaseHTTPMiddleware, dispatch=calc_process_time)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
