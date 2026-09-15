"""
Application middlewares.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.context import reset_request_id, set_request_id
from src.settings import settings


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    Request ID middleware.
    """
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        reset_request_id(token)


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
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=calc_process_time)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
