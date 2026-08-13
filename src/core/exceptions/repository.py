from collections.abc import Iterable

from src.core.enums import ModelActionEnum
from src.core.models.type_vars import ModelType
from src.core.type_vars import IdType

from .business_error import BusinessLogicException

__all__ = (
    "ModelIntegrityError",
    "ModelNotFoundError",
    "SortingFieldNotFoundError",
)


class ModelIntegrityError(BusinessLogicException):
    """
    Error for insert/update/delete operations.
    """

    def __init__(
        self,
        model: type[ModelType] | str,
        action: ModelActionEnum,
        *args: object,
        message: str | None = None,
    ) -> None:
        super().__init__(*args)
        self.model = model
        self.action = action
        self.message = message

    @property
    def msg(self) -> str:
        model_name = self.model if isinstance(self.model, str) else self.model.__name__
        msg = "Integrity error"
        match self.action:
            case ModelActionEnum.INSERT:
                msg += f" for model {model_name} insert."
            case ModelActionEnum.UPDATE:
                msg += f" for model {model_name} update."
            case ModelActionEnum.UPSERT:
                msg += f" for model {model_name} insert or update."
            case ModelActionEnum.DELETE:
                msg += f" for model {model_name} delete."
        if self.message is not None:
            msg += f" {self.message}."
        return msg


class ModelNotFoundError(BusinessLogicException):
    """
    Error if model not found.
    """

    def __init__(
        self,
        model: type[ModelType] | str,
        *args: object,
        model_id: IdType | Iterable[IdType] | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(*args)
        self.model = model
        self.message = message
        self.model_id = model_id

    @property
    def msg(self) -> str:
        model_name = self.model if isinstance(self.model, str) else self.model.__name__
        if self.message is not None:
            return self.message
        msg = f"Unable to find {model_name} model"
        if self.model_id is not None:
            if isinstance(self.model_id, Iterable):
                return f"{msg} with ids: [{', '.join(map(str, self.model_id))}]"
            return f"{msg} with id: {self.model_id}"
        return msg


class SortingFieldNotFoundError(BusinessLogicException):
    """
    Error if model does not have sorting field.
    """

    def __init__(
        self,
        field: str,
        *args: object,
        allowed_fields: str | None = None,
    ) -> None:
        super().__init__(*args)
        self.field = field
        self.allowed_fields = allowed_fields

    @property
    def msg(self) -> str:
        msg = f"Sorting field not found {self.field!r}."
        if self.allowed_fields is not None:
            msg += f" Allowed fields: {self.allowed_fields}."
        return msg
