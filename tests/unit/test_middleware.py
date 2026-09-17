"""
Tests for `src.middleware` (and, through it, `src.core.context`).

Both middlewares only produce anything once a response exists, so they are
tested through a real request rather than by calling `dispatch` with a double.
`httpx.ASGITransport` runs the whole stack without the lifespan, so nothing
here needs a container.

The request-id contextvar is asserted from the test itself on purpose:
`ASGITransport` awaits the application in the calling task, and
`BaseHTTPMiddleware` runs its dispatch function there too, so the value the
middleware sets is visible - and has to be cleaned up - in this very context.
"""

import httpx
import pytest
from fastapi import FastAPI

from src.core.context import get_request_id
from src.middleware import apply_middleware
from src.settings import settings


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    apply_middleware(app)

    @app.get("/echo")
    async def _echo() -> dict[str, str]:
        # Read from inside the request, which is the only place the contextvar
        # is supposed to hold anything.
        return {"request_id": get_request_id()}

    return app


@pytest.fixture
async def client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestRequestId:
    async def test_echoes_an_incoming_request_id_unchanged(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        The header is how a trace survives a hop: a gateway that already
        assigned an id must find that same id in the log lines and in the
        response, not a second one minted here.
        """
        response = await client.get("/echo", headers={"X-Request-ID": "from-gateway"})

        assert response.headers["X-Request-ID"] == "from-gateway"
        assert response.json()["request_id"] == "from-gateway"

    async def test_generates_a_request_id_when_the_header_is_absent(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        response = await client.get("/echo")

        request_id = response.headers["X-Request-ID"]
        assert request_id
        assert response.json()["request_id"] == request_id

    async def test_generated_ids_differ_between_requests(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        A constant would make the header useless for correlating anything.
        """
        first = await client.get("/echo")
        second = await client.get("/echo")

        assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]

    async def test_resets_the_contextvar_after_the_request(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        Why `reset_request_id` sits in a `finally`: without it the id of the
        last request stays in the context and gets stamped on whatever runs
        there next - background work, or the next request served from the same
        context.
        """
        assert get_request_id() == "-"

        await client.get("/echo", headers={"X-Request-ID": "leaky"})

        assert get_request_id() == "-"

    async def test_resets_the_contextvar_when_the_handler_raises(
        self,
        app: FastAPI,
    ) -> None:
        """
        The failing request is the one whose id matters most, and it is the one
        that skips every cleanup written after the `yield`-less happy path.
        """

        @app.get("/boom")
        async def _boom() -> None:
            raise RuntimeError("boom")

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            await client.get("/boom", headers={"X-Request-ID": "leaky"})

        assert get_request_id() == "-"


class TestProcessTime:
    async def test_reports_the_elapsed_time_as_a_float(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        response = await client.get("/echo")

        # Parsed rather than pattern-matched: the header is read by dashboards,
        # so it has to stay a bare number of seconds with no unit suffix.
        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0.0


class TestCors:
    async def test_allows_a_configured_origin(self, client: httpx.AsyncClient) -> None:
        """
        `apply_middleware` wires CORS from `settings.cors_origins`, and the
        browser only ever sees the effect of that through this header.
        """
        origin = settings.cors_origins[0]

        response = await client.get("/echo", headers={"Origin": origin})

        assert response.headers["access-control-allow-origin"] == origin
