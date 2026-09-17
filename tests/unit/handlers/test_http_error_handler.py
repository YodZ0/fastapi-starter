"""
Tests for `src.handlers.http_error_handler`.

The status code each business error maps to is part of the API contract, and
nothing below the HTTP layer can pin it: the handlers only ever run when
Starlette dispatches to them, so every test here drives a real request through
a real application.

The application is assembled by hand - `FastAPI()` plus
`apply_exception_handlers` - rather than taken from `create_app()`, because the
routes that raise have to be registered somewhere, and adding them to the
production app would ship them.

No container, no Postgres and no Redis: `httpx.ASGITransport` does not send
the ASGI lifespan events, so the application is exercised without its startup
ever running.
"""

import httpx
import pytest
from fastapi import FastAPI

from src.core.enums import ModelActionEnum
from src.core.exceptions import (
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
    SearchFieldNotFoundError,
    SortingFieldNotFoundError,
)
from src.handlers import apply_exception_handlers
from src.settings import settings

# Carried by the exception `/boom` raises. A business error's `msg` is written
# for the caller and is meant to go out; the text of an *unhandled* one is not,
# so this is the string the disclosure tests look for.
SECRET = "internal-detail-that-must-not-leak"


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    apply_exception_handlers(app)

    @app.get("/model-not-found")
    async def _model_not_found() -> None:
        raise ModelNotFoundError("Widget", model_id=1)

    @app.get("/model-integrity")
    async def _model_integrity() -> None:
        raise ModelIntegrityError("Widget", ModelActionEnum.INSERT)

    @app.get("/model-id-required")
    async def _model_id_required() -> None:
        raise ModelIdRequiredError("Widget", schema="WidgetUpdateSchema")

    @app.get("/sorting-field")
    async def _sorting_field() -> None:
        raise SortingFieldNotFoundError("nope", allowed_fields=["name"])

    @app.get("/search-field")
    async def _search_field() -> None:
        raise SearchFieldNotFoundError("nope", allowed_fields=["name"])

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError(SECRET)

    return app


@pytest.fixture
async def client(app: FastAPI):
    """
    `raise_app_exceptions=False` is what makes `/boom` testable: Starlette's
    `ServerErrorMiddleware` re-raises after handing the response to the
    transport, and the default transport would surface that in the test instead
    of the 500 the client actually receives.
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def debug(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    """
    Flip `settings.debug` for the duration of one test.

    The handlers read the module-level singleton, so patching the attribute on
    that object is what they see - there is no seam to inject through.
    """
    enabled: bool = request.param
    monkeypatch.setattr(settings, "debug", enabled)
    return enabled


class TestStatusCodes:
    """
    One case per registered handler. A wrong code here is an API break that no
    type checker and no unit test below the transport can catch.
    """

    @pytest.mark.parametrize(
        ("path", "expected_status"),
        [
            ("/model-not-found", 404),
            ("/model-integrity", 422),
            ("/model-id-required", 400),
            ("/sorting-field", 400),
            ("/search-field", 400),
            ("/boom", 500),
        ],
    )
    async def test_maps_the_error_to_its_status(
        self,
        client: httpx.AsyncClient,
        path: str,
        expected_status: int,
    ) -> None:
        response = await client.get(path)

        assert response.status_code == expected_status

    async def test_business_errors_answer_with_the_exception_schema(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        The body shape is the other half of the contract: the handlers dump
        `BusinessLogicExceptionSchema`, so a client can branch on `type`
        instead of parsing `msg`.
        """
        response = await client.get("/model-not-found")

        detail = response.json()["detail"]
        assert detail["type"] == "model_not_found"
        assert detail["msg"]
        assert "traceback" in detail


class TestDebugDisclosure:
    """
    What the response is allowed to say about the failure depends on
    `settings.debug`, and getting it wrong leaks a traceback to whoever sends a
    malformed request in production. Both sides of the switch are pinned.
    """

    @pytest.mark.parametrize("debug", [True], indirect=True)
    async def test_internal_error_includes_the_message_in_debug(
        self,
        client: httpx.AsyncClient,
        debug: bool,
    ) -> None:
        response = await client.get("/boom")

        assert SECRET in response.json()["detail"]

    @pytest.mark.parametrize("debug", [False], indirect=True)
    async def test_internal_error_says_nothing_in_production(
        self,
        client: httpx.AsyncClient,
        debug: bool,
    ) -> None:
        """
        The catch-all sees arbitrary exceptions - a driver error carrying a
        connection string, an assertion quoting a row. Only the fixed sentence
        may go out.
        """
        response = await client.get("/boom")

        assert response.json()["detail"] == "Unexpected server error."

    @pytest.mark.parametrize("debug", [True], indirect=True)
    async def test_business_error_carries_a_traceback_in_debug(
        self,
        client: httpx.AsyncClient,
        debug: bool,
    ) -> None:
        response = await client.get("/model-not-found")

        traceback = response.json()["detail"]["traceback"]
        assert traceback is not None
        assert "ModelNotFoundError" in traceback

    @pytest.mark.parametrize("debug", [False], indirect=True)
    async def test_business_error_omits_the_traceback_in_production(
        self,
        client: httpx.AsyncClient,
        debug: bool,
    ) -> None:
        """
        `msg` stays - it is written for the caller and names no internals - but
        the stack, with its file paths and local frames, does not.
        """
        response = await client.get("/model-not-found")

        detail = response.json()["detail"]
        assert detail["traceback"] is None
        assert detail["msg"]
