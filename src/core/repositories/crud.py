import contextlib
from typing import Generic, Sequence, cast

from sqlalchemy import select, insert, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.core.enums import ModelActionEnum
from src.core.exceptions import (
    ModelNotFoundError,
    ModelIntegrityError,
)
from src.core.type_vars import (
    ModelType,
    CreateSchemaBaseType,
    UpdateSchemaBaseType,
    ReadSchemaBaseType,
    IdType,
)


class CrudBaseRepository(
    Generic[
        ModelType,
        ReadSchemaBaseType,
        CreateSchemaBaseType,
        UpdateSchemaBaseType,
        IdType,
    ]
):
    model_type: type[ModelType]
    read_schema_type: type[ReadSchemaBaseType]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: IdType) -> ReadSchemaBaseType:
        """
        Получаем модель по идентификатору.
        """
        query = select(self.model_type).where(self.model_type.id == id)
        async with self._session as s:
            model = (await s.execute(query)).scalar_one_or_none()
            if model is None:
                raise ModelNotFoundError(self.model_type, model_id=id)
            return self._model_validate(model)

    async def get_one_or_none(self, id: IdType) -> ReadSchemaBaseType | None:
        """
        Получаем модель по идентификатору или None.
        """
        with contextlib.suppress(ModelNotFoundError):
            return await self.get(id)
        return None

    async def get_by_ids(
        self,
        ids: Sequence[IdType],
        *,
        strict: bool = False,
    ) -> list[ReadSchemaBaseType]:
        """
        Получаем список моделей по идентификаторам.
        """
        query = select(self.model_type).where(self.model_type.id.in_(ids))
        async with self._session as s:
            models = (await s.execute(query)).scalars().all()
            self._check_get_by_ids_strict(ids, models, strict)
            return [self._model_validate(model) for model in models]

    async def get_all(self) -> list[ReadSchemaBaseType]:
        """
        Получаем список всех моделей.
        """
        query = select(self.model_type)
        async with self._session as s:
            models = (await s.execute(query)).scalars().all()
            return [self._model_validate(model) for model in models]

    async def create(self, create_obj: CreateSchemaBaseType) -> ReadSchemaBaseType:
        """
        Создаем модель.
        """
        statement = (
            insert(self.model_type)
            .values(**create_obj.model_dump(exclude={"id"}))
            .returning(self.model_type)
        )
        async with self._session as s, s.begin():
            try:
                model = (await s.execute(statement)).scalar_one()
                return self._model_validate(model)
            except IntegrityError as integrity_error:
                raise ModelIntegrityError(
                    self.model_type,
                    ModelActionEnum.INSERT,
                ) from integrity_error

    async def update(self, update_obj: UpdateSchemaBaseType) -> ReadSchemaBaseType:
        """
        Обновляем модель по идентификатору.
        """
        pk = update_obj.id
        statement = (
            update(self.model_type)
            .where(self.model_type.id == pk)
            .values(**update_obj.model_dump(exclude={"id"}, exclude_unset=True))
            .returning(self.model_type)
        )
        async with self._session as s, s.begin():
            try:
                model = (await s.execute(statement)).scalar_one_or_none()
                if model is None:
                    raise ModelNotFoundError(self.model_type, model_id=update_obj.id)
                return self._model_validate(model)
            except IntegrityError as integrity_error:
                raise ModelIntegrityError(
                    self.model_type,
                    ModelActionEnum.UPDATE,
                ) from integrity_error

    async def delete(self, id: IdType) -> None:
        """
        Удаляем модель по идентификатору.
        """
        async with self._session as s, s.begin():
            statement = delete(self.model_type).where(self.model_type.id == id)
            await s.execute(statement)

    def _model_validate(self, model: ModelType, **kwargs) -> ReadSchemaBaseType:
        """
        Приводим модель к схеме.
        """
        return self.read_schema_type.model_validate(
            model,
            from_attributes=True,
            **kwargs,
        )

    def _check_get_by_ids_strict(
        self,
        ids: Sequence[IdType],
        models: Sequence[ModelType],
        strict: bool,
    ) -> None:
        """
        Проверяем, что по идентификаторам получены все модели.
        """
        if strict and len(ids) != len(models):
            raise ModelNotFoundError(
                self.model_type,
                model_id=set(ids) - {cast(IdType, model.id) for model in models},
            )
