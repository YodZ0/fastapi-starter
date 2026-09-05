from collections.abc import Iterable
from typing import TypeIs, assert_never

from src.core.database.type_vars import ModelType
from src.core.enums import ModelActionEnum
from src.core.type_vars import IdType

from .business_error import BusinessLogicException

__all__ = (
    "ModelIdRequiredError",
    "ModelIntegrityError",
    "ModelNotFoundError",
    "SearchFieldNotFoundError",
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
        msg = f"Integrity error for model {model_name}"
        match self.action:
            case ModelActionEnum.INSERT:
                msg += " insert."
            case ModelActionEnum.UPDATE:
                msg += " update."
            case ModelActionEnum.UPSERT:
                msg += " insert or update."
            case ModelActionEnum.DELETE:
                msg += " delete."
            case ModelActionEnum.BULK_INSERT:
                msg += " bulk insert."
            case ModelActionEnum.BULK_UPDATE:
                msg += " bulk update."
            case ModelActionEnum.BULK_DELETE:
                msg += " bulk delete."
            case _:
                # Not dead code: it is what makes mypy reject a new
                # ModelActionEnum member that nobody rendered here.
                assert_never(self.action)
        if self.message:
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
        msg = f"Unable to find {model_name} model"
        if self.model_id is not None:
            if not self._is_collection(self.model_id):
                msg += f" with id: {self.model_id}"
            else:
                ids = ", ".join(map(str, sorted(self.model_id)))
                msg += f" with ids: [{ids}]"
        if self.message:
            msg += f". {self.message}"
        return msg

    @staticmethod
    def _is_collection(
        value: IdType | Iterable[IdType],
    ) -> TypeIs[list[IdType] | set[IdType] | tuple[IdType, ...]]:
        """
        Narrow `model_id` to the collection forms the callers pass.

        The return type spells out the concrete containers instead of
        `Iterable[IdType]`, because `str` is itself an `Iterable[str]`: the wider
        annotation would let mypy treat a plain string id as narrowed away in
        the `else` branch, which is the opposite of what this check does.
        """
        return isinstance(value, (list, set, tuple))


class ModelIdRequiredError(BusinessLogicException):
    """
    Error if an update was requested without an identifier.

    Update schemas keep `id` optional so that a schema can be built field by
    field, which means the repository has to reject the missing one itself
    instead of letting it reach the WHERE clause.
    """

    def __init__(
        self,
        model: type[ModelType] | str,
        *args: object,
        schema: str | None = None,
    ) -> None:
        super().__init__(*args)
        self.model = model
        self.schema = schema

    @property
    def msg(self) -> str:
        model_name = self.model if isinstance(self.model, str) else self.model.__name__
        msg = f"Model {model_name} cannot be updated without an id."
        if self.schema:
            msg += f" Set it on the {self.schema} schema."
        return msg


class SortingFieldNotFoundError(BusinessLogicException):
    """
    Error if model does not have sorting field.
    """

    def __init__(
        self,
        field: str,
        *args: object,
        allowed_fields: Iterable[str] | str | None = None,
    ) -> None:
        super().__init__(*args)
        self.field = field
        self.allowed_fields = allowed_fields

    @property
    def msg(self) -> str:
        msg = f"Sorting field not found {self.field!r}."

        if self.allowed_fields:
            if isinstance(self.allowed_fields, str):
                fields_str = self.allowed_fields
            else:
                fields_str = ", ".join(self.allowed_fields)

            msg += f" Allowed fields: {fields_str}."
        else:
            msg += " No sorting fields are allowed."
        return msg


class SearchFieldNotFoundError(BusinessLogicException):
    """
    Error if model does not have search field.
    """

    def __init__(
        self,
        field: str,
        *args: object,
        allowed_fields: Iterable[str] | str | None = None,
    ) -> None:
        super().__init__(*args)
        self.field = field
        self.allowed_fields = allowed_fields

    @property
    def msg(self) -> str:
        msg = f"Search field not found {self.field!r}."

        if self.allowed_fields:
            if isinstance(self.allowed_fields, str):
                fields_str = self.allowed_fields
            else:
                fields_str = ", ".join(self.allowed_fields)

            msg += f" Allowed fields: {fields_str}."
        else:
            msg += " No searching fields are allowed."
        return msg
