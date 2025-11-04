import uuid
from typing import TypeVar

from .models.base import Base
from .schemas import (
    ReadSchemaInt,
    CreateSchemaInt,
    UpdateSchemaInt,
    ReadSchemaUUID,
    CreateSchemaUUID,
    UpdateSchemaUUID,
)

ModelType = TypeVar("ModelType", bound=Base, covariant=True)
ReadSchemaBaseType = TypeVar(
    "ReadSchemaBaseType",
    bound=ReadSchemaInt | ReadSchemaUUID,
)
CreateSchemaBaseType = TypeVar(
    "CreateSchemaBaseType",
    bound=CreateSchemaInt | CreateSchemaUUID,
)
UpdateSchemaBaseType = TypeVar(
    "UpdateSchemaBaseType",
    bound=UpdateSchemaInt | UpdateSchemaUUID,
)
IdType = TypeVar("IdType", bound=int | uuid.UUID)
