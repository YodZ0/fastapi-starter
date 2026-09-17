"""
Tests for `src.apps.healthz`.

The endpoint is trivial; its address is not. It is what a load balancer, a
compose healthcheck or a Kubernetes probe is pointed at, so the path here is
assembled from `settings.api` instead of being spelled out - a changed prefix
then fails in this test rather than in a deployment whose probes have quietly
gone red.

The application is the real `create_app()`, so the route has to survive the
whole router assembly to be reachable. Its container is closed on teardown,
exactly as in the `created_app` fixture of `tests/unit/test_bootstrap.py`;
`ASGITransport` never starts the lifespan, so nothing else is opened.
"""

import httpx
import pytest
from fastapi import FastAPI

from src.bootstrap import create_app
from src.core.schemas import StatusOKResponseSchema
from src.settings import settings

HEALTHZ_PATH = f"{settings.api.prefix}{settings.api.v1.prefix}/healthz"


@pytest.fixture
async def app():
    app = create_app()
    yield app
    await app.state.dishka_container.close()


@pytest.fixture
async def client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestHealthz:
    async def test_answers_ok(self, client: httpx.AsyncClient) -> None:
        response = await client.get(HEALTHZ_PATH)

        assert response.status_code == 200

    async def test_answers_with_the_status_schema(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        Validated against the schema rather than compared to a literal dict:
        the response model is serialized by alias, so the wire format follows
        `RequestResponseSchema` and not the field names written here.
        """
        response = await client.get(HEALTHZ_PATH)

        assert StatusOKResponseSchema.model_validate(response.json()) == (
            StatusOKResponseSchema()
        )

    async def test_needs_no_database_or_cache(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        A liveness probe that touched Postgres or Redis would report the
        process dead whenever a dependency blipped - and a restart cannot fix
        a dependency. The whole module runs with neither service reachable
        (`tests/conftest.py` points the settings at unroutable hosts), so a
        dependency added to this route shows up here.
        """
        response = await client.get(HEALTHZ_PATH)

        assert response.status_code == 200
