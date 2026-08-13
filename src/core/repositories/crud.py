"""
CRUD repository for Postgres.

Every method returns a Pydantic read schema rather than an ORM model, so no
detached instance - and no lazy IO - escapes the repository.

Joined-table inheritance is supported through `__subtypes__`: reads use
`selectin_polymorphic`, and create/update/upsert/delete walk the parent chain
table by table.

The identifier is the *last* generic argument. That is what lets
`CRUDRepositoryInt` / `CRUDRepositoryUUID` pin it while `__init_subclass__`
keeps reading the first four arguments the same way.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from typing import Any, Generic, cast, get_args

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectin_polymorphic

from src.core.enums import ModelActionEnum
from src.core.exceptions.repository import (
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
    SearchFieldNotFoundError,
    SortingFieldNotFoundError,
)
from src.core.models.type_vars import ModelIntType, ModelUUIDType, ModelWithIdType
from src.core.schemas.pagination import PaginationResultSchema, PaginationSchema
from src.core.session_manager import SessionManager
from src.core.type_vars import IdType

from .type_vars import (
    CreateSchemaIntType,
    CreateSchemaType,
    CreateSchemaUUIDType,
    ReadSchemaIntType,
    ReadSchemaType,
    ReadSchemaUUIDType,
    UpdateSchemaIntType,
    UpdateSchemaType,
    UpdateSchemaUUIDType,
)

__all__ = (
    "CRUDRepository",
    "CRUDRepositoryInt",
    "CRUDRepositoryUUID",
)


class CRUDRepository(
    Generic[
        ModelWithIdType,
        ReadSchemaType,
        CreateSchemaType,
        UpdateSchemaType,
        IdType,
    ]
):
    """
    CRUD repository for Postgres.

    A concrete repository names its model and its three schemas as generic
    arguments; the metaprogramming in `__init_subclass__` reads them back at
    class-creation time, so no registration boilerplate is needed:

    ```python
    class UserRepository(
        CRUDRepositoryUUID[User, UserReadSchema, UserCreateSchema, UserUpdateSchema]
    ):
        search_fields = ("email", "name")
    ```

    For joined-table inheritance, list the children in `__subtypes__`; the
    repository then dispatches on the concrete schema type it is handed and
    returns the matching read schema for every row it loads.
    """

    __abstract__: bool = True

    #: Joined-table-inheritance children, as
    #: `(model, read schema, create schema, update schema)`.
    __subtypes__: Sequence[
        tuple[
            type[ModelWithIdType],
            type[ReadSchemaType],
            type[CreateSchemaType],
            type[UpdateSchemaType],
        ]
    ] = ()

    #: Columns `paginate(search=...)` scans when no explicit `search_by` given.
    search_fields: Sequence[str] = ()

    model: type[ModelWithIdType]
    model_types: set[type[ModelWithIdType]]
    model_subtypes: set[type[ModelWithIdType]]
    read_schemas_mapping: dict[type[ModelWithIdType], type[ReadSchemaType]]
    create_models_mapping: dict[type[CreateSchemaType], type[ModelWithIdType]]
    update_models_mapping: dict[type[UpdateSchemaType], type[ModelWithIdType]]
    model_identities_mapping: dict[Any, type[ModelWithIdType]]

    def __init__(self, session_manager: SessionManager) -> None:
        if getattr(self, "__abstract__", False):
            raise TypeError(f"Can't instantiate abstract class {type(self).__name__}")
        self._session_manager = session_manager

    def __init_subclass__(cls, **kwargs: object) -> None:
        """
        Resolve the model and the schemas from the generic base.

        Runs once per subclass. Abstract intermediates (`__abstract__ = True` in
        their own body) are skipped: they carry type variables, not real types.
        """
        super().__init_subclass__(**kwargs)

        if cls.__dict__.get("__abstract__", False):
            return
        cls.__abstract__ = False

        # `cls.__dict__`, not `getattr`: `__orig_bases__` is inherited, so
        # `class Repo(CRUDRepositoryUUID)` - no arguments - would otherwise read
        # the base's own type variables and register them as if they were a
        # model and its schemas.
        base_generic = next(
            (
                base
                for base in cls.__dict__.get("__orig_bases__", ())
                if issubclass(getattr(base, "__origin__", base), CRUDRepository)
            ),
            None,
        )
        if base_generic is None:
            # Nothing to resolve here. Extending a repository that is already
            # concrete is fine - every mapping is inherited - but a subclass of
            # an abstract base with no arguments has nothing to inherit.
            if not isinstance(getattr(cls, "model", None), type):
                raise TypeError(
                    f"{cls.__name__} must inherit from CRUDRepository with generics."
                )
            return
        # `[:4]` covers both spellings: the full base takes a fifth argument for
        # the identifier, the Int/UUID variants have already pinned it.
        generic_args = get_args(base_generic)[:4]
        if len(generic_args) != 4:
            raise TypeError(f"{cls.__name__} is missing generic type arguments.")

        registrations = [*cls.__subtypes__, cast(Any, generic_args)]

        cls.model = generic_args[0]
        cls.model_types = set()
        cls.model_subtypes = {subtype[0] for subtype in cls.__subtypes__}
        cls.read_schemas_mapping = {}
        cls.create_models_mapping = {}
        cls.update_models_mapping = {}
        cls.model_identities_mapping = {}

        for model, read_schema, create_schema, update_schema in registrations:
            cls.model_types.add(model)
            cls.read_schemas_mapping[model] = read_schema
            cls.create_models_mapping[create_schema] = model
            cls.update_models_mapping[update_schema] = model
            mapper = getattr(model, "__mapper__", None)
            identity = getattr(mapper, "polymorphic_identity", None)
            if identity is not None:
                cls.model_identities_mapping[identity] = model

    # --- READ ---

    async def get(self, obj_id: IdType) -> ReadSchemaType:
        """
        Get one model by ID.
        """
        async with self._session_manager.get_session() as s:
            query = self.select().where(self.model.id == obj_id)
            model = (await s.execute(query)).scalar_one_or_none()
            if model is None:
                raise ModelNotFoundError(self.model, model_id=obj_id)
            return self.model_validate(model)

    async def get_or_none(self, obj_id: IdType) -> ReadSchemaType | None:
        """
        Get one model by ID or None.
        """
        with suppress(ModelNotFoundError):
            return await self.get(obj_id)
        return None

    async def get_multi(
        self,
        obj_ids: Sequence[IdType],
        *,
        strict: bool = False,
    ) -> list[ReadSchemaType]:
        """
        Get models by IDs.

        With `strict=True` a missing ID is an error instead of a short result.
        """
        if not obj_ids:
            return []

        async with self._session_manager.get_session() as s:
            query = self.select().where(self.model.id.in_(obj_ids))
            models = (await s.execute(query)).scalars().all()
            self.check_get_multi_strict(obj_ids, models, strict=strict)
            return self.models_validate(models)

    async def get_all(
        self,
        *,
        sorting: Iterable[str] | None = None,
    ) -> list[ReadSchemaType]:
        """
        Get all models.
        """
        async with self._session_manager.get_session() as s:
            query = self._sort(self.select(), sorting or ())
            models = (await s.execute(query)).scalars().all()
            return self.models_validate(models)

    async def paginate(
        self,
        pagination: PaginationSchema,
        *,
        search: str | None = None,
        search_by: Iterable[str] | None = None,
        sorting: Iterable[str] | None = None,
    ) -> PaginationResultSchema[ReadSchemaType]:
        """
        Get a page of models together with the total count.
        """
        return await self.paginate_with_filter(
            pagination,
            search=search,
            search_by=search_by,
            sorting=sorting,
        )

    async def paginate_with_filter(
        self,
        pagination: PaginationSchema,
        *,
        search: str | None = None,
        search_by: Iterable[str] | None = None,
        sorting: Iterable[str] | None = None,
        select_filter: Callable[
            [sa.Select[tuple[ModelWithIdType]]],
            sa.Select[tuple[ModelWithIdType]],
        ]
        | None = None,
    ) -> PaginationResultSchema[ReadSchemaType]:
        """
        Same as `paginate`, with a hook for repository-specific filtering.

        Subclasses use it to add their own WHERE/JOIN without reimplementing
        counting and paging:

        ```python
        return await self.paginate_with_filter(
            pagination,
            select_filter=lambda query: query.where(User.is_active),
        )
        ```
        """
        query = self.select()
        if select_filter is not None:
            query = select_filter(query)
        if search:
            query = self._search(query, search, search_by)

        async with self._session_manager.get_session() as s:
            # Counted through a subquery rather than `with_only_columns`: the
            # filter hook is free to add joins, and wrapping keeps the count
            # honest whatever shape the query ended up in.
            #
            # Two statements on purpose - folding the total into the page with
            # `count(*) OVER ()` is slower, not faster. The window has to see
            # every matching row before LIMIT applies, so the page loses its
            # index scan and gets a full WindowAgg instead.
            # The window only breaks even where the query already scans everything
            # anyway (an ILIKE search, say), and it reports no total at all once
            # the offset runs past the last row.
            count_query = sa.select(sa.func.count()).select_from(query.subquery())
            count = (await s.execute(count_query)).scalar_one()
            page_query = self._paginate(self._sort(query, sorting or ()), pagination)
            models = (await s.execute(page_query)).scalars().all()
            return PaginationResultSchema(
                objects=self.models_validate(models),
                count=count,
            )

    # --- WRITE ---

    async def create(self, create_schema: CreateSchemaType) -> ReadSchemaType:
        """
        Create and return one model.
        """
        model = self._model_for_create(create_schema)
        create_dict = self._dump_create_schema(create_schema)
        async with self._session_manager.get_session() as s:
            try:
                created = await self._bulk_create_with_model(model, [create_dict], s)
            except IntegrityError as e:
                raise ModelIntegrityError(self.model, ModelActionEnum.INSERT) from e
            return created[0]

    async def bulk_create(
        self,
        create_schemas: Sequence[CreateSchemaType],
    ) -> list[ReadSchemaType]:
        """
        Create several models, returned in the order they were passed in.
        """
        if not create_schemas:
            return []

        # Grouped by model *and* by column set: a multi-row INSERT renders a
        # single VALUES clause, so every dict in one batch has to carry the same
        # keys - which stops being true as soon as `id` is dropped from some.
        groups: defaultdict[
            tuple[type[ModelWithIdType], tuple[str, ...]],
            list[tuple[int, dict[str, Any]]],
        ] = defaultdict(list)
        for index, create_schema in enumerate(create_schemas):
            create_dict = self._dump_create_schema(create_schema)
            key = (self._model_for_create(create_schema), tuple(sorted(create_dict)))
            groups[key].append((index, create_dict))

        created: list[ReadSchemaType | None] = [None] * len(create_schemas)
        async with self._session_manager.get_session() as s:
            try:
                for (model, _), batch in groups.items():
                    schemas = await self._bulk_create_with_model(
                        model,
                        [create_dict for _, create_dict in batch],
                        s,
                    )
                    for (index, _), schema in zip(batch, schemas, strict=True):
                        created[index] = schema
            except IntegrityError as e:
                raise ModelIntegrityError(
                    self.model,
                    ModelActionEnum.BULK_INSERT,
                ) from e
        return cast(list[ReadSchemaType], created)

    async def update(self, update_schema: UpdateSchemaType) -> ReadSchemaType:
        """
        Update one model.

        The ID is taken from the schema, and only the fields that were
        explicitly set are written (`exclude_unset=True`).
        """
        obj_id = self._require_id(update_schema)
        model = self._model_for_update(update_schema)
        update_dict = update_schema.model_dump(exclude_unset=True)
        update_dict["id"] = obj_id
        async with self._session_manager.get_session() as s:
            try:
                return await self._update_with_model(model, update_dict, s)
            except IntegrityError as e:
                raise ModelIntegrityError(self.model, ModelActionEnum.UPDATE) from e

    async def bulk_update(self, update_schemas: Sequence[UpdateSchemaType]) -> None:
        """
        Update several models with one executemany per batch.

        Partial like `update`: only the fields that were explicitly set are
        written. An executemany needs the same parameter keys for all of its
        rows, so the schemas are batched by the set of fields they touch - two
        schemas setting different fields simply become two statements, instead
        of one statement writing NULL over everything left unset.
        """
        if not update_schemas:
            return

        groups: defaultdict[
            tuple[type[ModelWithIdType], tuple[str, ...]],
            list[dict[str, Any]],
        ] = defaultdict(list)
        for update_schema in update_schemas:
            update_dict = update_schema.model_dump(exclude_unset=True)
            update_dict["id"] = self._require_id(update_schema)
            key = (self._model_for_update(update_schema), tuple(sorted(update_dict)))
            groups[key].append(update_dict)

        async with self._session_manager.get_session() as s:
            try:
                for (model, _), batch in groups.items():
                    await self._bulk_update_with_model(model, batch, s)
            except IntegrityError as e:
                raise ModelIntegrityError(
                    self.model,
                    ModelActionEnum.BULK_UPDATE,
                ) from e

    async def upsert(self, create_schema: CreateSchemaType) -> ReadSchemaType:
        """
        Create a model, or update it if its ID is already taken.
        """
        model = self._model_for_create(create_schema)
        create_dict = self._dump_create_schema(create_schema)
        async with self._session_manager.get_session() as s:
            try:
                return await self._upsert_with_model(model, create_dict, s)
            except IntegrityError as e:
                raise ModelIntegrityError(self.model, ModelActionEnum.UPSERT) from e

    async def delete(self, obj_id: IdType, *, strict: bool = False) -> None:
        """
        Delete one model by ID.
        """
        await self.bulk_delete([obj_id], strict=strict)

    async def bulk_delete(
        self,
        obj_ids: Sequence[IdType],
        *,
        strict: bool = False,
    ) -> None:
        """
        Delete models by IDs.

        With `strict=True` an ID that matches nothing is an error.
        """
        if not obj_ids:
            return

        async with self._session_manager.get_session() as s:
            try:
                if strict:
                    await self._check_ids_exist(obj_ids, s)
                # Deepest table first: a child row holds an FK to its parent.
                for model in await self._models_to_delete(obj_ids, s):
                    await s.execute(sa.delete(model).where(model.id.in_(obj_ids)))
            except IntegrityError as e:
                raise ModelIntegrityError(
                    self.model,
                    ModelActionEnum.BULK_DELETE,
                ) from e

    # --- QUERY BUILDING ---

    @classmethod
    def select(cls) -> sa.Select[tuple[ModelWithIdType]]:
        """
        Select the model, pulling in the columns of every registered subtype.
        """
        query = sa.select(cls.model)
        if cls.model_subtypes:
            return query.options(
                selectin_polymorphic(cls.model, list(cls.model_subtypes))
            )
        return query

    @classmethod
    def model_validate(cls, model: ModelWithIdType) -> ReadSchemaType:
        """
        Convert a model into the read schema registered for its exact type.
        """
        read_schema = cls.read_schemas_mapping.get(type(model))
        if read_schema is None:
            raise TypeError(
                f"{type(model).__name__} has no read schema in {cls.__name__}; "
                f"add it to __subtypes__."
            )
        return read_schema.model_validate(model, from_attributes=True)

    @classmethod
    def models_validate(cls, models: Sequence[ModelWithIdType]) -> list[ReadSchemaType]:
        """
        Convert models into read schemas.
        """
        return [cls.model_validate(model) for model in models]

    @classmethod
    def check_get_multi_strict(
        cls,
        obj_ids: Sequence[IdType],
        models: Sequence[ModelWithIdType],
        *,
        strict: bool,
    ) -> None:
        """
        Check that a model was found for every requested ID.
        """
        if strict and len(obj_ids) != len(models):
            raise ModelNotFoundError(
                cls.model,
                model_id=set(obj_ids) - {cast(IdType, model.id) for model in models},
            )

    @staticmethod
    def _paginate(
        query: sa.Select[tuple[ModelWithIdType]],
        pagination: PaginationSchema,
    ) -> sa.Select[tuple[ModelWithIdType]]:
        """
        Apply pagination to a SELECT query.
        """
        return query.limit(pagination.limit).offset(pagination.offset)

    def _sort(
        self,
        query: sa.Select[tuple[ModelWithIdType]],
        sorting: Iterable[str],
    ) -> sa.Select[tuple[ModelWithIdType]]:
        """
        Apply sorting to a SELECT query. A leading `-` means descending.
        """
        order_by: list[sa.UnaryExpression[Any]] = []
        for field in sorting:
            descending = field.startswith("-")
            name = field[1:] if descending else field
            column = getattr(self.model, name, None)
            if column is None:
                raise SortingFieldNotFoundError(field)
            order_by.append(column.desc() if descending else column.asc())
        if not order_by:
            return query
        return query.order_by(*order_by)

    def _search(
        self,
        query: sa.Select[tuple[ModelWithIdType]],
        search: str,
        search_by: Iterable[str] | None,
    ) -> sa.Select[tuple[ModelWithIdType]]:
        """
        Apply a case-insensitive substring search over the given columns.
        """
        fields = tuple(search_by if search_by is not None else self.search_fields)
        if not fields:
            raise SearchFieldNotFoundError(
                "search_by",
                allowed_fields="set `search_fields` on the repository "
                "or pass `search_by` explicitly",
            )
        condition: sa.ColumnElement[bool] = sa.false()
        for field in fields:
            column = getattr(self.model, field, None)
            if column is None:
                raise SearchFieldNotFoundError(field)
            condition = sa.or_(condition, column.ilike(f"%{search}%"))
        return query.where(condition)

    # --- TYPE DISPATCH ---

    @classmethod
    def _model_for_create(
        cls,
        create_schema: CreateSchemaType,
    ) -> type[ModelWithIdType]:
        """
        Find the model a create schema belongs to.
        """
        model = cls.create_models_mapping.get(type(create_schema))
        if model is None:
            raise TypeError(
                f"{type(create_schema).__name__} is not registered "
                f"in {cls.__name__}; add it to __subtypes__."
            )
        return model

    @classmethod
    def _model_for_update(
        cls,
        update_schema: UpdateSchemaType,
    ) -> type[ModelWithIdType]:
        """
        Find the model an update schema belongs to.
        """
        model = cls.update_models_mapping.get(type(update_schema))
        if model is None:
            raise TypeError(
                f"{type(update_schema).__name__} is not registered "
                f"in {cls.__name__}; add it to __subtypes__."
            )
        return model

    @classmethod
    def _require_id(cls, update_schema: UpdateSchemaType) -> IdType:
        """
        Read the identifier an update needs, or fail with a clear error.
        """
        obj_id = update_schema.id
        if obj_id is None:
            raise ModelIdRequiredError(
                cls.model,
                schema=type(update_schema).__name__,
            )
        # The schema is generic over its own identifier, so `id` arrives as Any;
        # the repository is the place that knows which one it is.
        return cast(IdType, obj_id)

    @classmethod
    def _get_parent_model(
        cls,
        model: type[ModelWithIdType],
    ) -> type[ModelWithIdType] | None:
        """
        Get the model of the parent table, for joined-table inheritance.

        Only models registered on this repository count: anything else is a
        declarative base, which has no table of its own.
        """
        if not model.__bases__ or model.__bases__[0] not in cls.model_types:
            return None
        return model.__bases__[0]

    @staticmethod
    def _dump_create_schema(create_schema: CreateSchemaType) -> dict[str, Any]:
        """
        Dump a create schema, dropping the ID when it was not set.

        Leaving `id: None` in would override the server-side default.
        """
        create_dict = create_schema.model_dump()
        if create_dict.get("id") is None:
            create_dict.pop("id", None)
        return create_dict

    # --- PER-TABLE STATEMENTS ---

    @classmethod
    async def _bulk_create_with_model(
        cls,
        model: type[ModelWithIdType],
        create_dicts: list[dict[str, Any]],
        session: AsyncSession,
    ) -> list[ReadSchemaType]:
        """
        INSERT one batch into one table, parents first.
        """
        parent_dicts = await cls._bulk_create_parent(model, create_dicts, session)
        columns = model.__table__.columns
        values: list[dict[str, Any]] = []
        for create_dict, parent_dict in zip(create_dicts, parent_dicts, strict=True):
            value = {k: v for k, v in create_dict.items() if k in columns}
            if "id" in parent_dict:
                value["id"] = parent_dict["id"]
            values.append(value)

        statement = sa.insert(model).values(values).returning(*columns.values())
        rows = (await session.execute(statement)).mappings().all()
        read_schema = cls.read_schemas_mapping[model]
        return [
            read_schema.model_validate({**parent_dict, **row})
            for parent_dict, row in zip(parent_dicts, rows, strict=True)
        ]

    @classmethod
    async def _bulk_create_parent(
        cls,
        model: type[ModelWithIdType],
        create_dicts: list[dict[str, Any]],
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        INSERT the parent rows, so their generated IDs can be reused.
        """
        parent_model = cls._get_parent_model(model)
        if parent_model is None:
            return [{} for _ in create_dicts]
        parents = await cls._bulk_create_with_model(parent_model, create_dicts, session)
        return [parent.model_dump() for parent in parents]

    @classmethod
    async def _update_with_model(
        cls,
        model: type[ModelWithIdType],
        update_dict: dict[str, Any],
        session: AsyncSession,
    ) -> ReadSchemaType:
        """
        UPDATE one row of one table, parents first.
        """
        parent_dict = await cls._update_parent(model, update_dict, session)
        columns = model.__table__.columns
        obj_id = update_dict["id"]
        values = {k: v for k, v in update_dict.items() if k != "id" and k in columns}

        statement: sa.Executable
        if values:
            statement = (
                sa.update(model)
                .where(model.id == obj_id)
                .values(values)
                .returning(*columns.values())
            )
        else:
            # Nothing to write at this level - normal for the parent half of a
            # partial update. An UPDATE with an empty SET is a SQLAlchemy error,
            # so read the row back instead.
            statement = sa.select(*columns.values()).where(model.id == obj_id)

        row = (await session.execute(statement)).mappings().one_or_none()
        if row is None:
            raise ModelNotFoundError(model, model_id=obj_id)
        return cls.read_schemas_mapping[model].model_validate({**parent_dict, **row})

    @classmethod
    async def _update_parent(
        cls,
        model: type[ModelWithIdType],
        update_dict: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        UPDATE the parent row.
        """
        parent_model = cls._get_parent_model(model)
        if parent_model is None:
            return {}
        parent = await cls._update_with_model(parent_model, update_dict, session)
        return parent.model_dump()

    @classmethod
    async def _bulk_update_with_model(
        cls,
        model: type[ModelWithIdType],
        update_dicts: list[dict[str, Any]],
        session: AsyncSession,
    ) -> None:
        """
        UPDATE many rows of one table by primary key, parents first.
        """
        await cls._bulk_update_parent(model, update_dicts, session)
        columns = model.__table__.columns
        values = [
            {k: v for k, v in update_dict.items() if k in columns}
            for update_dict in update_dicts
        ]
        # Nothing but the primary key reaches this table: SQLAlchemy would
        # refuse the statement, and there is nothing to write anyway.
        if not any(set(value) - {"id"} for value in values):
            return
        # `update()` with no values plus a parameter list is the ORM's bulk
        # UPDATE by primary key, which is why every dict carries its `id`.
        await session.execute(sa.update(model), values)

    @classmethod
    async def _bulk_update_parent(
        cls,
        model: type[ModelWithIdType],
        update_dicts: list[dict[str, Any]],
        session: AsyncSession,
    ) -> None:
        """
        UPDATE the parent rows.
        """
        parent_model = cls._get_parent_model(model)
        if parent_model is not None:
            await cls._bulk_update_with_model(parent_model, update_dicts, session)

    @classmethod
    async def _upsert_with_model(
        cls,
        model: type[ModelWithIdType],
        create_dict: dict[str, Any],
        session: AsyncSession,
    ) -> ReadSchemaType:
        """
        INSERT ... ON CONFLICT DO UPDATE one row of one table, parents first.
        """
        parent_dict = await cls._upsert_parent(model, create_dict, session)
        columns = model.__table__.columns
        values = {k: v for k, v in create_dict.items() if k in columns}
        if "id" in parent_dict:
            values["id"] = parent_dict["id"]

        primary_keys = [column.name for column in model.__table__.primary_key]
        conflict_values = {k: v for k, v in values.items() if k not in primary_keys}
        statement: Insert = insert(model).values(values)
        if conflict_values:
            statement = statement.on_conflict_do_update(
                index_elements=primary_keys,
                set_=conflict_values,
            )
        else:
            # Every column of this table belongs to its primary key: there is
            # nothing to overwrite, so a conflict just means "already there".
            statement = statement.on_conflict_do_nothing(index_elements=primary_keys)

        result = await session.execute(statement.returning(*columns.values()))
        row = result.mappings().one_or_none()
        if row is None:
            row = await cls._read_row(model, values, session)
        return cls.read_schemas_mapping[model].model_validate({**parent_dict, **row})

    @classmethod
    async def _upsert_parent(
        cls,
        model: type[ModelWithIdType],
        create_dict: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Upsert the parent row.
        """
        parent_model = cls._get_parent_model(model)
        if parent_model is None:
            return {}
        parent = await cls._upsert_with_model(parent_model, create_dict, session)
        return parent.model_dump()

    @classmethod
    async def _read_row(
        cls,
        model: type[ModelWithIdType],
        values: dict[str, Any],
        session: AsyncSession,
    ) -> sa.RowMapping:
        """
        Read back the row a DO NOTHING upsert declined to touch.
        """
        obj_id = values.get("id")
        if obj_id is None:
            raise ModelIntegrityError(
                cls.model,
                ModelActionEnum.UPSERT,
                message="the conflicting row could not be identified",
            )
        columns = model.__table__.columns
        statement = sa.select(*columns.values()).where(model.id == obj_id)
        return (await session.execute(statement)).mappings().one()

    @classmethod
    async def _models_to_delete(
        cls,
        obj_ids: Sequence[IdType],
        session: AsyncSession,
    ) -> list[type[ModelWithIdType]]:
        """
        List the tables a delete has to touch, deepest first.

        A non-polymorphic model is one table. A polymorphic one needs the rows
        of whichever children the IDs actually point at, plus everything in
        between them and the base.
        """
        models: list[type[ModelWithIdType]] = [cls.model]
        polymorphic_on = cls.model.__mapper__.polymorphic_on
        if polymorphic_on is None:
            return models

        statement = (
            sa.select(polymorphic_on).where(cls.model.id.in_(obj_ids)).distinct()
        )
        identities = (await session.execute(statement)).scalars().all()
        for identity in identities:
            model = cls.model_identities_mapping.get(identity)
            while model is not None and model not in models:
                models.append(model)
                model = cls._get_parent_model(model)
        return sorted(models, key=lambda m: len(m.__mro__), reverse=True)

    @classmethod
    async def _check_ids_exist(
        cls,
        obj_ids: Sequence[IdType],
        session: AsyncSession,
    ) -> None:
        """
        Check that every ID matches a row.
        """
        statement = sa.select(cls.model.id).where(cls.model.id.in_(obj_ids))
        found = set((await session.execute(statement)).scalars().all())
        missing = set(obj_ids) - found
        if missing:
            raise ModelNotFoundError(cls.model, model_id=missing)


class CRUDRepositoryInt(
    CRUDRepository[
        ModelIntType,
        ReadSchemaIntType,
        CreateSchemaIntType,
        UpdateSchemaIntType,
        int,
    ],
    Generic[
        ModelIntType,
        ReadSchemaIntType,
        CreateSchemaIntType,
        UpdateSchemaIntType,
    ],
):
    """
    CRUD repository for models keyed by an integer.
    """

    __abstract__ = True


class CRUDRepositoryUUID(
    CRUDRepository[
        ModelUUIDType,
        ReadSchemaUUIDType,
        CreateSchemaUUIDType,
        UpdateSchemaUUIDType,
        uuid.UUID,
    ],
    Generic[
        ModelUUIDType,
        ReadSchemaUUIDType,
        CreateSchemaUUIDType,
        UpdateSchemaUUIDType,
    ],
):
    """
    CRUD repository for models keyed by a UUID.
    """

    __abstract__ = True
