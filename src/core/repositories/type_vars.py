from typing import TypeVar

from src.core.schemas import (
    BaseSchema,
    CreateSchemaInt,
    CreateSchemaUUID,
    ReadSchemaInt,
    ReadSchemaUUID,
    UpdateSchemaInt,
    UpdateSchemaUUID,
)

ReadSchemaBaseType = TypeVar(
    "ReadSchemaBaseType",
    bound=ReadSchemaInt | ReadSchemaUUID | BaseSchema,
)
CreateSchemaBaseType = TypeVar(
    "CreateSchemaBaseType",
    bound=CreateSchemaInt | CreateSchemaUUID | BaseSchema,
)
UpdateSchemaBaseType = TypeVar(
    "UpdateSchemaBaseType",
    bound=UpdateSchemaInt | UpdateSchemaUUID | BaseSchema,
)
