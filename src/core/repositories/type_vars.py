"""
Type variables of the repository layer.
"""

from typing import Any, TypeVar

from src.core.schemas import (
    CreateSchemaGeneric,
    CreateSchemaInt,
    CreateSchemaUUID,
    ReadSchemaGeneric,
    ReadSchemaInt,
    ReadSchemaUUID,
    UpdateSchemaGeneric,
    UpdateSchemaInt,
    UpdateSchemaUUID,
)

# Bound to the generic bases instead of the int/UUID pair: that keeps `.id`
# visible to the type checker for any identifier type, including the `str` keys
# IdType allows.

ReadSchemaType = TypeVar("ReadSchemaType", bound=ReadSchemaGeneric[Any])
CreateSchemaType = TypeVar("CreateSchemaType", bound=CreateSchemaGeneric[Any])
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=UpdateSchemaGeneric[Any])

ReadSchemaIntType = TypeVar("ReadSchemaIntType", bound=ReadSchemaInt)
CreateSchemaIntType = TypeVar("CreateSchemaIntType", bound=CreateSchemaInt)
UpdateSchemaIntType = TypeVar("UpdateSchemaIntType", bound=UpdateSchemaInt)

ReadSchemaUUIDType = TypeVar("ReadSchemaUUIDType", bound=ReadSchemaUUID)
CreateSchemaUUIDType = TypeVar("CreateSchemaUUIDType", bound=CreateSchemaUUID)
UpdateSchemaUUIDType = TypeVar("UpdateSchemaUUIDType", bound=UpdateSchemaUUID)
