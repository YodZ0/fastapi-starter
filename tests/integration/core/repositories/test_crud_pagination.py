"""
`paginate` and `paginate_with_filter`: limit/offset, the total count, search
and the filter hook.
"""

import pytest

from src.core.exceptions import SearchFieldNotFoundError, SortingFieldNotFoundError
from src.core.schemas import PaginationSchema
from tests.integration.models import Widget
from tests.integration.repositories import (
    GadgetRepository,
    VehicleRepository,
    WidgetRepository,
)


def page(limit: int, offset: int = 0) -> PaginationSchema:
    return PaginationSchema(limit=limit, offset=offset)


class TestPageWindow:
    async def test_returns_at_most_limit_rows(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        LIMIT decides the page size.
        """
        result = await widget_repo.paginate(page(limit=2), sorting=("id",))

        assert len(result.objects) == 2

    async def test_offset_skips_the_earlier_rows(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Sorted explicitly: without an ORDER BY, OFFSET has no defined meaning.
        """
        first_page = await widget_repo.paginate(page(limit=2), sorting=("id",))
        second_page = await widget_repo.paginate(
            page(limit=2, offset=2),
            sorting=("id",),
        )

        assert [schema.slug for schema in first_page.objects] == ["alpha", "beta"]
        assert [schema.slug for schema in second_page.objects] == ["gamma"]

    async def test_count_is_the_total_not_the_page_size(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The count is what the caller renders "page 1 of N" from, so it has to
        ignore LIMIT and OFFSET entirely - it is a second statement over the
        unpaged query for exactly that reason.
        """
        result = await widget_repo.paginate(page(limit=1))

        assert len(result.objects) == 1
        assert result.count == len(seed.widgets)

    async def test_an_offset_past_the_end_still_reports_the_total(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The page is empty but the total is not zero. Folding the count into the
        page with a window function would report nothing here, which is the
        concrete reason the two statements are kept apart.
        """
        result = await widget_repo.paginate(page(limit=10, offset=100))

        assert result.objects == []
        assert result.count == len(seed.widgets)

    async def test_sorting_applies_to_the_page(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Sorting runs before the window, so a descending sort changes which rows
        land on the first page, not just their order within it.
        """
        result = await widget_repo.paginate(page(limit=1), sorting=("-weight",))

        assert [schema.slug for schema in result.objects] == ["gamma"]

    async def test_rejects_an_unknown_sorting_field(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Same guard as on `get_all`, reached through the pagination path.
        """
        with pytest.raises(SortingFieldNotFoundError):
            await widget_repo.paginate(page(limit=10), sorting=("nonexistent",))


class TestSearch:
    async def test_scans_the_repository_search_fields_by_default(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `WidgetRepository.search_fields` is `("name", "description")`, and a term
        that only matches `description` proves both columns are in the OR.
        """
        result = await widget_repo.paginate(page(limit=10), search="second")

        assert [schema.slug for schema in result.objects] == ["beta"]

    async def test_matches_on_a_substring(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The term is wrapped in `%` on both sides, so it does not have to anchor.
        """
        result = await widget_repo.paginate(page(limit=10), search="widget")

        assert len(result.objects) == len(seed.widgets)

    @pytest.mark.parametrize(
        "search",
        ["alpha", "ALPHA", "AlPhA"],
        ids=("lowercase", "uppercase", "mixed_case"),
    )
    async def test_ignores_case(
        self,
        widget_repo: WidgetRepository,
        seed,
        search,
    ) -> None:
        """
        ILIKE, not LIKE: a search box is not a case-sensitive interface.
        """
        result = await widget_repo.paginate(page(limit=10), search=search)

        assert [schema.slug for schema in result.objects] == ["alpha"]

    async def test_an_explicit_search_by_overrides_the_default_fields(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Narrowing to `name` alone has to actually exclude `description`, which
        is only visible with a term that lives in the column being dropped.
        """
        result = await widget_repo.paginate(
            page(limit=10),
            search="second",
            search_by=("name",),
        )

        assert result.objects == []

    async def test_count_reflects_the_search_not_the_table(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The count is taken from the searched query, so a filtered page does not
        report the size of the whole table.
        """
        result = await widget_repo.paginate(page(limit=10), search="alpha")

        assert result.count == 1

    async def test_an_empty_search_term_is_no_search_at_all(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `if search:` rather than `if search is not None:` - an empty box from a
        query string means "no filter", not "match rows containing nothing".
        """
        result = await widget_repo.paginate(page(limit=10), search="")

        assert result.count == len(seed.widgets)

    async def test_rejects_a_field_the_model_does_not_have(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `search_by` arrives from outside, so an unknown column has to fail as a
        business error rather than an `AttributeError`.
        """
        with pytest.raises(SearchFieldNotFoundError) as exc_info:
            await widget_repo.paginate(
                page(limit=10),
                search="alpha",
                search_by=("nonexistent",),
            )

        assert exc_info.value.field == "nonexistent"

    async def test_rejects_a_search_on_a_repository_with_no_search_fields(
        self,
        vehicle_repo: VehicleRepository,
        seed,
    ) -> None:
        """
        `VehicleRepository` declares no `search_fields`. Without the guard the
        condition would compile to `WHERE false` and silently return nothing, so
        it is refused with a message that says how to fix it.
        """
        with pytest.raises(SearchFieldNotFoundError) as exc_info:
            await vehicle_repo.paginate(page(limit=10), search="sedan")

        assert exc_info.value.field == "search_by"

    async def test_rejects_an_explicitly_empty_search_by(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        An empty `search_by` overrides the repository's own fields rather than
        falling back to them, so it hits the same guard even where
        `search_fields` is configured.
        """
        with pytest.raises(SearchFieldNotFoundError) as exc_info:
            await widget_repo.paginate(
                page(limit=10),
                search="alpha",
                search_by=(),
            )

        assert exc_info.value.field == "search_by"

    async def test_works_on_a_uuid_keyed_repository(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        Nothing in the search or count path depends on the identifier type.
        """
        result = await gadget_repo.paginate(page(limit=10), search="beta")

        assert [schema.code for schema in result.objects] == ["B-2"]
        assert result.count == 1


class TestPaginateWithFilter:
    async def test_applies_the_filter_to_the_page(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The hook exists so a subclass can add its own WHERE without
        reimplementing counting and paging.
        """
        result = await widget_repo.paginate_with_filter(
            page(limit=10),
            select_filter=lambda query: query.where(Widget.weight >= 20),
        )

        assert {schema.slug for schema in result.objects} == {"beta", "gamma"}

    async def test_counts_after_the_filter_rather_than_before(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The count is built from the already-filtered query. If it were taken
        from the bare table instead, the caller would page through rows that do
        not exist.
        """
        result = await widget_repo.paginate_with_filter(
            page(limit=1),
            select_filter=lambda query: query.where(Widget.weight >= 20),
        )

        assert len(result.objects) == 1
        assert result.count == 2

    async def test_combines_with_search_and_sorting(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The filter narrows, the search narrows further, and the sort orders
        whatever is left - all three have to survive in the same query.
        """
        result = await widget_repo.paginate_with_filter(
            page(limit=10),
            search="widget",
            sorting=("-weight",),
            select_filter=lambda query: query.where(Widget.weight >= 20),
        )

        assert [schema.slug for schema in result.objects] == ["gamma", "beta"]
        assert result.count == 2

    async def test_no_filter_is_the_same_as_paginate(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `paginate` is this method with the hook left out, so the two have to
        agree when it is.
        """
        filtered = await widget_repo.paginate_with_filter(
            page(limit=10),
            sorting=("id",),
        )
        plain = await widget_repo.paginate(page(limit=10), sorting=("id",))

        assert filtered == plain
