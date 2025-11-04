import traceback
from abc import ABC, abstractmethod

from typing import Iterable

from src.core.utils import to_snake_case
from src.core.enums import ModelActionEnum
from src.core.type_vars import ModelType, IdType
from src.core.schemas import (
    BusinessLogicExceptionSchema,
    ModelAlreadyExistsErrorSchema,
)


class BusinessLogicException(Exception, ABC):
    """
    Базовое исключение бизнес-логики.
    """

    @property
    def type(self) -> str:
        """
        Тип ошибки.
        """
        return to_snake_case(type(self).__name__.replace("Error", ""))

    @property
    @abstractmethod
    def msg(self) -> str:
        """
        Сообщение ошибки.
        """
        ...

    def __str__(self) -> str:
        return self.msg

    def get_schema(self, debug: bool) -> BusinessLogicExceptionSchema:
        """
        Получаем схему исключения.
        """
        return BusinessLogicExceptionSchema(
            type=self.type,
            msg=self.msg,
            traceback=(
                "".join(
                    traceback.format_exception(type(self), self, self.__traceback__)
                )
                if debug
                else None
            ),
        )


class ModelNotFoundError(BusinessLogicException):
    """
    Ошибка, возникающая при невозможности найти модель.
    """

    def __init__(
        self,
        model: type[ModelType] | str,
        *args: object,
        model_id: IdType | Iterable[IdType] | None = None,
        model_name: str | Iterable[str] | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(*args)
        self.model = model
        self.model_id = model_id
        self.model_name = model_name
        self.custom_message = message

    @property
    def msg(self) -> str:
        if self.custom_message is not None:
            return self.custom_message
        msg = f"Не удалось найти модель {self.model if isinstance(self.model, str) else self.model.__name__}"
        if self.model_id is not None:
            if isinstance(self.model_id, Iterable):
                return (
                    f'{msg} по идентификаторам: [{", ".join(map(str, self.model_id))}]'
                )
            return f"{msg} по идентификатору: {self.model_id}"
        if self.model_name is not None:
            if isinstance(self.model_name, Iterable):
                return f'{msg} по именам: [{", ".join(self.model_name)}]'
            return f"{msg} по имени: {self.model_name}"
        return msg


class ModelAlreadyExistsError(BusinessLogicException):
    """
    Ошибка, возникающая при попытке создать модель с существующим уникальным полем.
    """

    def __init__(self, field: str, message: str, *args: object) -> None:
        super().__init__(*args)
        self.field = field
        self.message = message

    @property
    def msg(self) -> str:
        return self.message

    def get_schema(self, debug: bool) -> BusinessLogicExceptionSchema:
        return ModelAlreadyExistsErrorSchema.model_validate(
            {**super().get_schema(debug).model_dump(), "field": self.field}
        )


class ModelIntegrityError(BusinessLogicException):
    """
    Ошибка целостности данных при взаимодействии с моделью.
    """

    def __init__(
        self,
        model: type[ModelType] | str,
        action: ModelActionEnum,
        *args: object,
    ) -> None:
        super().__init__(*args)
        self.model = model
        self.action = action

    @property
    def msg(self) -> str:
        """
        Сообщение ошибки.
        """
        msg = "Ошибка целостности данных"
        model_name = self.model if isinstance(self.model, str) else self.model.__name__
        match self.action:
            case ModelActionEnum.INSERT:
                msg += f" при создании модели {model_name}"
            case ModelActionEnum.UPDATE:
                msg += f" при изменении модели {model_name}"
            case ModelActionEnum.UPSERT:
                msg += f" при создании или изменении модели {model_name}"
            case ModelActionEnum.DELETE:
                msg += f" при удалении модели {model_name}"
        return msg
