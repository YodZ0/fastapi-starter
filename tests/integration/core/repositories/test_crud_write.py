"""
Write side of `CRUDRepository`: `create`, `update`, `upsert`, `delete` and
their bulk counterparts.
"""

import uuid

import pytest

from src.core.enums import ModelActionEnum
from src.core.exceptions import (
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
)
from tests.integration.models import (
    GadgetCreateSchema,
    GadgetUpdateSchema,
    Widget,
    WidgetCreateSchema,
    WidgetUpdateSchema,
)
from tests.integration.repositories import GadgetRepository, WidgetRepository

MISSING_ID = 10_000_000
MISSING_UUID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")


class TestCreate:
    async def test_returns_the_row_the_database_filled_in(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The INSERT uses RETURNING, so the identity value and the timestamp
        defaults come back on the same round trip - no follow-up SELECT, and no
        `None` left in the schema the caller receives.
        """
        result = await widget_repo.create(
            WidgetCreateSchema(name="Delta widget", slug="delta", weight=40)
        )

        assert result.id is not None
        assert result.name == "Delta widget"
        assert result.description is None
        assert result.created_at is not None
        assert result.updated_at is not None

    async def test_the_created_row_can_be_read_back(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The savepoint the write opened is released, not rolled back, so the next
        call sees the row.
        """
        created = await widget_repo.create(
            WidgetCreateSchema(name="Delta widget", slug="delta", weight=40)
        )

        assert (await widget_repo.get(created.id)).slug == "delta"

    async def test_translates_a_unique_violation_into_a_business_error(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        A driver-level `IntegrityError` must not reach the caller: the layers
        above only know the business hierarchy.
        """
        taken_slug = seed.widgets[0].slug

        with pytest.raises(ModelIntegrityError) as exc_info:
            await widget_repo.create(
                WidgetCreateSchema(name="Clash", slug=taken_slug, weight=1)
            )

        assert exc_info.value.model is Widget
        assert exc_info.value.action is ModelActionEnum.INSERT

    async def test_a_failed_create_leaves_earlier_rows_alone(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Each call runs in its own savepoint, so a rejected INSERT rolls back
        only itself and the session stays usable afterwards.
        """
        await widget_repo.create(
            WidgetCreateSchema(name="Delta widget", slug="delta", weight=40)
        )

        with pytest.raises(ModelIntegrityError):
            await widget_repo.create(
                WidgetCreateSchema(name="Clash", slug="delta", weight=1)
            )

        assert len(await widget_repo.get_all()) == len(seed.widgets) + 1


class TestBulkCreate:
    async def test_returns_an_empty_list_for_no_schemas(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The short circuit keeps an INSERT with no VALUES out of the database.
        """
        assert await widget_repo.bulk_create([]) == []

    async def test_inserts_every_schema(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        One statement, several rows.
        """
        result = await widget_repo.bulk_create(
            [
                WidgetCreateSchema(name="Delta", slug="delta", weight=40),
                WidgetCreateSchema(name="Epsilon", slug="epsilon", weight=50),
            ]
        )

        assert [schema.slug for schema in result] == ["delta", "epsilon"]
        assert len(await widget_repo.get_all()) == len(seed.widgets) + 2

    async def test_returns_rows_in_the_order_they_were_passed(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        Schemas are grouped by the set of columns they touch, because one
        multi-row INSERT renders one VALUES clause and cannot mix shapes. That
        grouping shuffles the rows into batches, and this is what proves the
        result is put back into the order the caller passed.

        Gadget, not Widget: a `BaseInt` key is `GENERATED ALWAYS`, so the only
        way to get two different column sets here is a UUID key that some
        schemas name explicitly and some leave to the server default.
        """
        explicit_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        schemas = [
            GadgetCreateSchema(name="No id A", code="N-1"),
            GadgetCreateSchema(id=explicit_id, name="With id", code="W-1"),
            GadgetCreateSchema(name="No id B", code="N-2"),
        ]

        result = await gadget_repo.bulk_create(schemas)

        assert [schema.code for schema in result] == ["N-1", "W-1", "N-2"]
        assert result[1].id == explicit_id

    async def test_translates_a_unique_violation_into_a_business_error(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Same contract as `create`, but the action has to name the bulk variant
        so the message points at the right call.
        """
        with pytest.raises(ModelIntegrityError) as exc_info:
            await widget_repo.bulk_create(
                [
                    WidgetCreateSchema(name="Delta", slug="delta", weight=40),
                    WidgetCreateSchema(name="Clash", slug="delta", weight=41),
                ]
            )

        assert exc_info.value.action is ModelActionEnum.BULK_INSERT


class TestUpdate:
    async def test_writes_only_the_fields_that_were_set(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The update is partial (`exclude_unset=True`). A field the caller never
        mentioned must keep its value rather than be overwritten with the
        schema's `None` default.
        """
        widget = seed.widgets[0]

        result = await widget_repo.update(WidgetUpdateSchema(id=widget.id, weight=99))

        assert result.weight == 99
        assert result.name == widget.name
        assert result.slug == widget.slug
        assert result.description == widget.description

    async def test_can_write_an_explicit_none(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The flip side: a `None` that was passed on purpose is a value, and
        `exclude_unset` is what keeps it apart from a field left out entirely.
        """
        widget = seed.widgets[0]

        result = await widget_repo.update(
            WidgetUpdateSchema(id=widget.id, description=None)
        )

        assert result.description is None
        assert result.name == widget.name

    async def test_the_change_is_visible_to_a_later_read(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The UPDATE is committed by its own savepoint, not left pending in one.
        """
        widget = seed.widgets[0]

        await widget_repo.update(WidgetUpdateSchema(id=widget.id, name="Renamed"))

        assert (await widget_repo.get(widget.id)).name == "Renamed"

    async def test_rejects_a_schema_without_an_id(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Update schemas keep `id` optional so that a schema can be built field by
        field, which leaves the repository to reject the missing one before it
        reaches the WHERE clause.
        """
        with pytest.raises(ModelIdRequiredError) as exc_info:
            await widget_repo.update(WidgetUpdateSchema(name="Nameless"))

        assert exc_info.value.schema == "WidgetUpdateSchema"

    async def test_raises_when_the_id_matches_nothing(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        An UPDATE that hits no row is silent in SQL; RETURNING is what lets the
        repository notice and say so.
        """
        with pytest.raises(ModelNotFoundError) as exc_info:
            await widget_repo.update(WidgetUpdateSchema(id=MISSING_ID, weight=1))

        assert exc_info.value.model_id == MISSING_ID

    async def test_translates_a_unique_violation_into_a_business_error(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Updating into a taken unique value is the same class of failure as
        inserting one.
        """
        with pytest.raises(ModelIntegrityError) as exc_info:
            await widget_repo.update(
                WidgetUpdateSchema(id=seed.widgets[0].id, slug=seed.widgets[1].slug)
            )

        assert exc_info.value.action is ModelActionEnum.UPDATE


class TestBulkUpdate:
    async def test_does_nothing_for_no_schemas(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        No schemas, no statement - and nothing changed.
        """
        await widget_repo.bulk_update([])

        assert len(await widget_repo.get_all()) == len(seed.widgets)

    async def test_updates_every_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        One executemany for rows that touch the same columns.
        """
        await widget_repo.bulk_update(
            [
                WidgetUpdateSchema(id=seed.widgets[0].id, weight=101),
                WidgetUpdateSchema(id=seed.widgets[1].id, weight=102),
            ]
        )

        result = await widget_repo.get_all(sorting=("id",))
        assert [schema.weight for schema in result[:2]] == [101, 102]

    async def test_schemas_with_different_fields_do_not_null_each_other_out(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The reason `bulk_update` batches by field set at all.

        An executemany needs the same parameter keys for every row, so folding
        these two into one statement would write NULL over whatever the other
        schema left unset. Two statements is the correct answer, and the only
        way to see the difference is to check the untouched columns afterwards.
        """
        first, second = seed.widgets[0], seed.widgets[1]

        await widget_repo.bulk_update(
            [
                WidgetUpdateSchema(id=first.id, weight=101),
                WidgetUpdateSchema(id=second.id, name="Renamed beta"),
            ]
        )

        updated_first = await widget_repo.get(first.id)
        updated_second = await widget_repo.get(second.id)

        assert (updated_first.weight, updated_first.name) == (101, first.name)
        assert (updated_second.weight, updated_second.name) == (
            second.weight,
            "Renamed beta",
        )

    async def test_a_schema_carrying_only_an_id_is_a_no_op(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Nothing but the primary key reaches the table. SQLAlchemy refuses an
        UPDATE with an empty SET, so the repository has to drop the statement
        itself rather than let that error out.
        """
        widget = seed.widgets[0]

        await widget_repo.bulk_update([WidgetUpdateSchema(id=widget.id)])

        assert (await widget_repo.get(widget.id)).name == widget.name

    async def test_rejects_a_schema_without_an_id(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Every row is matched by primary key, so a schema without one has nothing
        to update.
        """
        with pytest.raises(ModelIdRequiredError):
            await widget_repo.bulk_update([WidgetUpdateSchema(weight=1)])

    async def test_translates_a_unique_violation_into_a_business_error(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Same contract as `update`, with the bulk action named.
        """
        with pytest.raises(ModelIntegrityError) as exc_info:
            await widget_repo.bulk_update(
                [
                    WidgetUpdateSchema(id=seed.widgets[0].id, slug="clash"),
                    WidgetUpdateSchema(id=seed.widgets[1].id, slug="clash"),
                ]
            )

        assert exc_info.value.action is ModelActionEnum.BULK_UPDATE


class TestUpsert:
    async def test_inserts_a_row_that_is_not_there_yet(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        No conflict, so `ON CONFLICT DO UPDATE` behaves as a plain INSERT.

        Gadget, not Widget: an explicit ID is the only way to make two calls
        collide, and `BaseInt.id` is `GENERATED ALWAYS` - Postgres rejects an
        INSERT that names it. The conflict half of `upsert` is therefore
        reachable only on models whose key can be chosen client-side.
        """
        obj_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        result = await gadget_repo.upsert(
            GadgetCreateSchema(id=obj_id, name="Fresh", code="F-1")
        )

        assert (result.id, result.name, result.code) == (obj_id, "Fresh", "F-1")

    async def test_overwrites_the_row_whose_id_is_already_taken(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        The conflict branch: the second write has to update in place rather than
        raise, and it has to return the new values.
        """
        gadget = seed.gadgets[0]

        result = await gadget_repo.upsert(
            GadgetCreateSchema(id=gadget.id, name="Overwritten", code="O-1")
        )

        assert result.id == gadget.id
        assert (result.name, result.code) == ("Overwritten", "O-1")

    async def test_the_overwrite_does_not_add_a_row(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        An upsert that resolves to an update leaves the row count alone, which
        is the whole difference from a create.
        """
        await gadget_repo.upsert(
            GadgetCreateSchema(id=seed.gadgets[0].id, name="Overwritten", code="O-1")
        )

        assert len(await gadget_repo.get_all()) == len(seed.gadgets)

    async def test_without_an_id_it_is_an_insert(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The ID is dropped from the dump when it was left unset, so the server
        default supplies one and no conflict is possible.
        """
        result = await widget_repo.upsert(
            WidgetCreateSchema(name="Delta widget", slug="delta", weight=40)
        )

        assert result.id is not None
        assert len(await widget_repo.get_all()) == len(seed.widgets) + 1

    async def test_translates_a_unique_violation_into_a_business_error(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        `ON CONFLICT` covers the primary key only; any other unique constraint
        still raises, and still has to arrive as a business error.
        """
        with pytest.raises(ModelIntegrityError) as exc_info:
            await gadget_repo.upsert(
                GadgetCreateSchema(
                    id=MISSING_UUID,
                    name="Clash",
                    code=seed.gadgets[0].code,
                )
            )

        assert exc_info.value.action is ModelActionEnum.UPSERT


class TestDelete:
    async def test_removes_the_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The basic case.
        """
        obj_id = seed.widgets[0].id

        await widget_repo.delete(obj_id)

        assert await widget_repo.get_or_none(obj_id) is None
        assert len(await widget_repo.get_all()) == len(seed.widgets) - 1

    async def test_is_silent_about_an_id_that_matches_nothing(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        Deleting something that is already gone reaches the desired end state,
        so by default it is not an error.
        """
        await widget_repo.delete(MISSING_ID)

        assert len(await widget_repo.get_all()) == len(seed.widgets)

    async def test_raises_on_a_missing_id_when_strict(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        `strict=True` is for callers that need to know the row was really there;
        the existence check runs before the DELETE.
        """
        with pytest.raises(ModelNotFoundError) as exc_info:
            await widget_repo.delete(MISSING_ID, strict=True)

        assert exc_info.value.model_id == {MISSING_ID}


class TestBulkDelete:
    async def test_removes_every_listed_row(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        One DELETE with an `IN`.
        """
        obj_ids = [seed.widgets[0].id, seed.widgets[1].id]

        await widget_repo.bulk_delete(obj_ids)

        assert [schema.id for schema in await widget_repo.get_all()] == [
            seed.widgets[2].id
        ]

    async def test_does_nothing_for_an_empty_list(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The short circuit keeps a DELETE with an empty `IN` out of the database.
        """
        await widget_repo.bulk_delete([])

        assert len(await widget_repo.get_all()) == len(seed.widgets)

    async def test_deletes_nothing_when_one_id_is_missing_and_strict(
        self,
        widget_repo: WidgetRepository,
        seed,
    ) -> None:
        """
        The check runs first and aborts the whole call, so a partly valid list
        does not leave a partly applied delete behind.
        """
        with pytest.raises(ModelNotFoundError):
            await widget_repo.bulk_delete(
                [seed.widgets[0].id, MISSING_ID],
                strict=True,
            )

        assert len(await widget_repo.get_all()) == len(seed.widgets)

    async def test_rows_are_deleted_by_uuid_too(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        The UUID-keyed repository takes the same path; the point is that the
        identifier type is not baked into the statement building.
        """
        await gadget_repo.bulk_delete([gadget.id for gadget in seed.gadgets])

        assert await gadget_repo.get_all() == []


class TestUuidRepository:
    async def test_create_lets_the_database_generate_the_key(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        `BaseUUID` carries both a Python-side `uuid4` default and a
        `gen_random_uuid()` server default; either way the caller gets a real
        key back without having to supply one.
        """
        result = await gadget_repo.create(GadgetCreateSchema(name="Fresh", code="F-1"))

        assert isinstance(result.id, uuid.UUID)
        assert (await gadget_repo.get(result.id)).code == "F-1"

    async def test_update_matches_on_the_uuid(
        self,
        gadget_repo: GadgetRepository,
        seed,
    ) -> None:
        """
        Partial updates work the same way as on an integer key.
        """
        gadget = seed.gadgets[0]

        result = await gadget_repo.update(
            GadgetUpdateSchema(id=gadget.id, name="Renamed")
        )

        assert (result.name, result.code) == ("Renamed", gadget.code)
