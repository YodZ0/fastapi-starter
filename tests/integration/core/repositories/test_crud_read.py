"""
Read side of `CRUDRepository`: `get`, `get_or_none`, `get_multi`, `get_all`.
"""

import pytest

from src.core.exceptions import ModelNotFoundError, SortingFieldNotFoundError
from tests.integration.models import Widget, WidgetReadSchema
from tests.integration.repositories import WidgetRepository

MISSING_ID = 10_000_000


class TestGet:
    async def test_returns_the_read_schema_for_the_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `get` hands back a Pydantic schema, never an ORM instance - that is what
        keeps a detached object, and its lazy IO, from escaping the repository.
        """
        widget = seed.widgets[0]

        result = await widget_repo.get(widget.id)

        assert isinstance(result, WidgetReadSchema)
        assert not isinstance(result, Widget)
        assert (result.id, result.name, result.slug) == (
            widget.id,
            widget.name,
            widget.slug,
        )

    async def test_raises_when_the_id_matches_nothing(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        A miss is an error, not a `None` the caller has to remember to check.
        """
        with pytest.raises(ModelNotFoundError) as exc_info:
            await widget_repo.get(MISSING_ID)

        assert exc_info.value.model is Widget
        assert exc_info.value.model_id == MISSING_ID


class TestGetOrNone:
    async def test_returns_the_row_when_it_exists(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The hit path is `get` verbatim.
        """
        result = await widget_repo.get_or_none(seed.widgets[1].id)

        assert result is not None
        assert result.id == seed.widgets[1].id

    async def test_returns_none_instead_of_raising_on_a_miss(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Only `ModelNotFoundError` is swallowed, and this is the call that proves
        the suppression is wired up at all.
        """
        assert await widget_repo.get_or_none(MISSING_ID) is None


class TestGetMulti:
    async def test_returns_every_requested_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The query is a single `IN`, so the result set - not its order, which no
        `ORDER BY` pins down - is what the caller gets.
        """
        obj_ids = [widget.id for widget in seed.widgets]

        result = await widget_repo.get_multi(obj_ids)

        assert {schema.id for schema in result} == set(obj_ids)

    async def test_returns_an_empty_list_for_no_ids(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The short circuit keeps an empty `IN ()` out of the database.
        """
        assert await widget_repo.get_multi([]) == []

    async def test_collapses_duplicate_ids_into_one_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `IN` deduplicates, so asking twice does not return the row twice.
        """
        obj_id = seed.widgets[0].id

        result = await widget_repo.get_multi([obj_id, obj_id])

        assert [schema.id for schema in result] == [obj_id]

    async def test_skips_missing_ids_when_not_strict(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The default is a short result rather than an error.
        """
        obj_id = seed.widgets[0].id

        result = await widget_repo.get_multi([obj_id, MISSING_ID])

        assert [schema.id for schema in result] == [obj_id]

    async def test_reports_exactly_the_missing_ids_when_strict(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `strict=True` exists so the caller does not have to diff the result
        against the request - the error already carries the difference.
        """
        obj_id = seed.widgets[0].id

        with pytest.raises(ModelNotFoundError) as exc_info:
            await widget_repo.get_multi([obj_id, MISSING_ID], strict=True)

        assert exc_info.value.model_id == {MISSING_ID}

    async def test_accepts_a_complete_id_set_when_strict(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Nothing missing, nothing raised.
        """
        obj_ids = [widget.id for widget in seed.widgets]

        result = await widget_repo.get_multi(obj_ids, strict=True)

        assert len(result) == len(obj_ids)


class TestGetAll:
    async def test_returns_every_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        No filter, no pagination.
        """
        result = await widget_repo.get_all()

        assert {schema.id for schema in result} == {w.id for w in seed.widgets}

    @pytest.mark.parametrize(
        ("sorting", "expected_slugs"),
        [
            (("weight",), ["alpha", "beta", "gamma"]),
            (("-weight",), ["gamma", "beta", "alpha"]),
            (("name",), ["alpha", "beta", "gamma"]),
        ],
        ids=("ascending", "descending", "by_another_column"),
    )
    async def test_orders_rows_by_the_requested_field(
        self,
        widget_repo: WidgetRepository,
        seed,
        sorting,
        expected_slugs,
    ) -> None:
        """
        A leading `-` is the only spelling for DESC, so both directions have to
        come out of the same string.
        """
        result = await widget_repo.get_all(sorting=sorting)

        assert [schema.slug for schema in result] == expected_slugs

    async def test_applies_several_sorting_fields_in_order(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The first field decides, the rest break ties - which is only observable
        with more than one of them in play.
        """
        result = await widget_repo.get_all(sorting=("description", "-weight"))

        # `description` is NULL for "gamma", and Postgres sorts NULLs last.
        assert [schema.slug for schema in result] == ["alpha", "beta", "gamma"]

    @pytest.mark.parametrize(
        "field",
        ["nonexistent", "-nonexistent"],
        ids=("ascending", "descending"),
    )
    async def test_rejects_a_field_the_model_does_not_have(
        self,
        widget_repo: WidgetRepository,
        seed,
        field,
    ) -> None:
        """
        Sorting fields reach the repository from the outside (a query string,
        usually), so an unknown one has to fail as a business error instead of
        an `AttributeError` or, worse, injected SQL.
        """
        with pytest.raises(SortingFieldNotFoundError) as exc_info:
            await widget_repo.get_all(sorting=(field,))

        assert exc_info.value.field == field
