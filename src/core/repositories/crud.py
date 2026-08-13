from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from typing import Any, Generic, cast, get_args

from sqlalchemy import Select, UnaryExpression, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from src.core.enums import ModelActionEnum
from src.core.exceptions.repository import (
    ModelIntegrityError,
    ModelNotFoundError,
    SortingFieldNotFoundError,
)
from src.core.models.type_vars import ModelWithIdType
from src.core.schemas.pagination import PaginationSchema
from src.core.session_manager import SessionManager
from src.core.type_vars import IdType

from .type_vars import CreateSchemaBaseType, UpdateSchemaBaseType


class CRUDRepository(
    Generic[
        IdType,
        ModelWithIdType,
        CreateSchemaBaseType,
        UpdateSchemaBaseType,
    ]
):
    """
    CRUD repository for Postgres.
    """

    __abstract__: bool = True
    __subtypes__: Sequence[
        tuple[
            type[ModelWithIdType],
            type[CreateSchemaBaseType],
            type[UpdateSchemaBaseType],
        ]
    ] = []

    model_types: set[type[ModelWithIdType]]
    model_subtypes: set[type[ModelWithIdType]]
    create_models_mapping: dict[type[CreateSchemaBaseType], type[ModelWithIdType]]
    update_models_mapping: dict[type[UpdateSchemaBaseType], type[ModelWithIdType]]
    model_identities_mapping: dict[Any, type[ModelWithIdType]]

    model: type[ModelWithIdType]

    def __init__(self, session_manager: SessionManager) -> None:
        if getattr(self, "__abstract__", False):
            raise TypeError(f"Can't instantiate abstract class {type(self).__name__}")
        self._session_manager = session_manager

    def __init_subclass__(cls, **kwargs: object) -> None:
        """
        Initialize the class.

        Get the SQLAlchemy model and Pydantic schema from the base type.
        """
        super().__init_subclass__(**kwargs)

        if cls.__dict__.get("__abstract__", False):
            return

        cls.__abstract__ = False

        base_repository_generic = next(
            (
                base
                for base in getattr(cls, "__orig_bases__", [])
                if issubclass(getattr(base, "__origin__", base), CRUDRepository)
            ),
            None,
        )
        if not base_repository_generic:
            raise ValueError(
                f"Class {cls.__name__} must inherit from CRUDRepository with generics."
            )
        generic_args = get_args(base_repository_generic)
        if len(generic_args) != 4:
            raise ValueError(f"{cls.__name__} is missing generic type arguments.")

        _id_type, model_type, create_schema_type, update_schema_type = generic_args
        subtypes_attr = getattr(cls, "__subtypes__", [])

        local_model_subtypes = {st[0] for st in subtypes_attr}
        local_model_types = set()
        local_create_models_mapping = {}
        local_update_models_mapping = {}
        local_model_identities_mapping = {}

        current_mapping = (model_type, create_schema_type, update_schema_type)
        types = [*subtypes_attr, current_mapping]

        for m_type, c_type, u_type in types:
            local_model_types.add(m_type)
            local_create_models_mapping[c_type] = m_type
            local_update_models_mapping[u_type] = m_type

            mapper = getattr(m_type, "__mapper__", None)
            if mapper and hasattr(mapper, "polymorphic_identity"):
                local_model_identities_mapping[mapper.polymorphic_identity] = m_type

        cls.model = model_type
        cls.model_subtypes = local_model_subtypes
        cls.model_types = local_model_types
        cls.create_models_mapping = local_create_models_mapping
        cls.update_models_mapping = local_update_models_mapping
        cls.model_identities_mapping = local_model_identities_mapping

        return

    async def get(self, obj_id: IdType) -> ModelWithIdType:
        """
        Get one model by ID.
        """
        async with self._session_manager.get_session() as s:
            query = select(self.model).where(self.model.id == obj_id)
            model = (await s.execute(query)).scalar_one_or_none()
            if model is None:
                raise ModelNotFoundError(model=self.model, model_id=obj_id)
            return model

    async def get_or_none(self, obj_id: IdType) -> ModelWithIdType | None:
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
    ) -> Sequence[ModelWithIdType]:
        """
        Get models by IDs.
        """
        if not obj_ids:
            return []

        async with self._session_manager.get_session() as s:
            query = select(self.model).where(self.model.id.in_(obj_ids))
            models = (await s.execute(query)).scalars().all()
            self.check_get_multi_strict(obj_ids, models, strict)
            return models

    async def get_all(
        self,
        pagination: PaginationSchema | None = None,
        sorting: Sequence[str] | None = None,
    ) -> Sequence[ModelWithIdType]:
        """
        Get all models with pagination and sorting.
        """
        async with self._session_manager.get_session() as s:
            query = select(self.model)

            if pagination is not None:
                query = self._paginate(query, pagination)
            if sorting is not None:
                query = self._sort(query, sorting)

            result = await s.execute(query)
            return result.scalars().all()

    async def create(self, create_schema: CreateSchemaBaseType) -> ModelWithIdType:
        """
        Create and return new model.
        """
        async with self._session_manager.get_session() as s:
            try:
                stmt = (
                    insert(self.model)
                    .values(**create_schema.model_dump())
                    .returning(self.model)
                )
                result = await s.execute(stmt)
                return result.scalar_one()
            except IntegrityError as e:
                raise ModelIntegrityError(
                    model=self.model,
                    action=ModelActionEnum.INSERT,
                ) from e

    async def bulk_create(
        self,
        objects_in: Sequence[CreateSchemaBaseType],
    ) -> Sequence[ModelWithIdType]:
        """
        Bulk create models.
        """
        if not objects_in:
            return []

        values = [obj.model_dump() for obj in objects_in]
        async with self._session_manager.get_session() as s:
            try:
                stmt = insert(self.model).values(values).returning(self.model)
                result = await s.execute(stmt)
                return result.scalars().all()
            except IntegrityError as e:
                raise ModelIntegrityError(
                    model=self.model,
                    action=ModelActionEnum.BULK_INSERT,
                ) from e

    async def update(
        self,
        obj_id: IdType,
        update_schema: UpdateSchemaBaseType,
    ) -> ModelWithIdType | None:
        """
        Update a record.
        Only the fields that were explicitly set are sent (exclude_unset=True).
        """
        update_data = update_schema.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_or_none(obj_id)
        async with self._session_manager.get_session() as s:
            try:
                stmt = (
                    update(self.model)
                    .where(self.model.id == obj_id)
                    .values(**update_data)
                    .returning(self.model)
                )
                result = await s.execute(stmt)
                return result.scalar_one_or_none()
            except IntegrityError as e:
                raise ModelIntegrityError(
                    model=self.model,
                    action=ModelActionEnum.UPDATE,
                ) from e

    async def bulk_update(self, update_data: Sequence[UpdateSchemaBaseType]) -> None:
        """
        Bulk update records (executemany).
        """
        if len(update_data) == 0:
            return

        update_dicts = [update_dict.model_dump() for update_dict in update_data]
        values: list[dict[str, Any]] = []
        for update_dict in update_dicts:
            values.append(
                {
                    k: v
                    for k, v in update_dict.items()
                    if k in self.model.__table__.columns
                }
            )

        async with self._session_manager.get_session() as s:
            try:
                stmt = update(self.model)
                await s.execute(stmt, values)
            except IntegrityError as e:
                raise ModelIntegrityError(
                    model=self.model,
                    action=ModelActionEnum.BULK_UPDATE,
                ) from e

    async def delete(self, obj_id: IdType) -> ModelWithIdType | None:
        """
        Delete a record by its ID.
        Returns the object if it existed, otherwise None.
        """
        async with self._session_manager.get_session() as s:
            stmt = (
                delete(self.model).where(self.model.id == obj_id).returning(self.model)
            )
            result = await s.execute(stmt)
            return result.scalar_one_or_none()

    async def bulk_delete(self, obj_ids: Sequence[IdType]) -> Sequence[ModelWithIdType]:
        """
        Bulk delete a group of records by a list of IDs.
        Returns the list of deleted objects.
        """
        if not obj_ids:
            return []

        async with self._session_manager.get_session() as s:
            stmt = (
                delete(self.model)
                .where(self.model.id.in_(obj_ids))
                .returning(self.model)
            )
            result = await s.execute(stmt)
            return result.scalars().all()

    @staticmethod
    def _paginate(
        query: Select[tuple[ModelWithIdType]],
        pagination: PaginationSchema,
    ) -> Select[tuple[ModelWithIdType]]:
        """
        Apply pagination to a SELECT query.
        """
        return query.limit(pagination.limit).offset(pagination.offset)

    def _sort(
        self,
        query: Select[tuple[ModelWithIdType]],
        sorting: Sequence[str],
    ) -> Select[tuple[ModelWithIdType]]:
        """
        Apply sorting to a SELECT query.
        """
        order_by_expr: list[UnaryExpression[Any]] = []
        for sf in sorting:
            try:
                if sf[0] == "-":
                    order_by_expr.append(getattr(self.model, sf[1:]).desc())
                else:
                    order_by_expr.append(getattr(self.model, sf))
            except AttributeError as attr_error:
                raise SortingFieldNotFoundError(sf) from attr_error
        return query.order_by(*order_by_expr)

    def check_get_multi_strict(
        self,
        ids: Sequence[IdType],
        models: Sequence[ModelWithIdType],
        strict: bool,
    ) -> None:
        """
        Check that a model was found for every requested ID.
        """
        if strict and len(ids) != len(models):
            raise ModelNotFoundError(
                self.model,
                model_id=set(ids) - {cast(IdType, model.id) for model in models},
            )
