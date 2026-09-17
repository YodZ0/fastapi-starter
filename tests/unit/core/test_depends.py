"""
Tests for `src.core.depends`.

`pagination_query` is exercised through a route rather than called directly:
its bounds live in `Query(ge=..., le=...)`, which is metadata FastAPI applies
while validating a request. A direct call would happily return `limit=0` and
prove nothing.
"""

import httpx
import pytest
from fastapi import FastAPI

from src.core.depends import Pagination


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    async def _items(pagination: Pagination) -> dict[str, int]:
        return {"limit": pagination.limit, "offset": pagination.offset}

    return app


@pytest.fixture
async def client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestDefaults:
    async def test_applies_a_page_size_when_no_query_is_given(
        self,
        client: httpx.AsyncClient,
    ) -> None:
        """
        The default is what protects an endpoint whose caller forgot to
        paginate: without it, the first unbounded list query is a full table
        scan serialized into a response.
        """
        response = await client.get("/items")

        assert response.status_code == 200
        assert response.json() == {"limit": 10, "offset": 0}


class TestBounds:
    @pytest.mark.parametrize(
        "query",
        [
            {"limit": 1},
            {"limit": 100},
            {"offset": 0},
            {"limit": 25, "offset": 50},
        ],
    )
    async def test_accepts_values_inside_the_range(
        self,
        client: httpx.AsyncClient,
        query: dict[str, int],
    ) -> None:
        response = await client.get("/items", params=query)

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "query",
        [
            {"limit": 0},  # an empty page is a client bug, not a valid request
            {"limit": 101},  # past the cap the ceiling stops meaning anything
            {"limit": -1},
            {"offset": -1},  # SQL has no negative OFFSET
        ],
    )
    async def test_rejects_values_outside_the_range(
        self,
        client: httpx.AsyncClient,
        query: dict[str, int],
    ) -> None:
        response = await client.get("/items", params=query)

        assert response.status_code == 422
