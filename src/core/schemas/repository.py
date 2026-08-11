import uuid
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

IdType = TypeVar("IdType")


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,  # validates schema from class attributes
        validate_by_name=True,  # allows to create schema with aliases its attribute
        validate_assignment=True,  # validates types if schema already created
    )


class CreateSchemaGeneric[IdType](BaseSchema):
    """
    Create model schema generic.
    """


class ReadSchemaGeneric[IdType](BaseSchema):
    """
    Read model schema generic.
    """

    id: IdType


class UpdateSchemaGeneric[IdType](BaseSchema):
    """
    Update model schema generic.
    """

    id: IdType | None = None  # need for bulk_update


class CreateSchemaInt(CreateSchemaGeneric[int]):
    """
    Create model schema with int id type.
    """


class ReadSchemaInt(ReadSchemaGeneric[int]):
    """
    Read model schema with int id type.
    """


class UpdateSchemaInt(UpdateSchemaGeneric[int]):
    """
    Update model schema with int id type.
    """


class CreateSchemaUUID(CreateSchemaGeneric[uuid.UUID]):
    """
    Create model schema with UUID id type.
    """


class ReadSchemaUUID(ReadSchemaGeneric[uuid.UUID]):
    """
    Read model schema with UUID id type.
    """


class UpdateSchemaUUID(UpdateSchemaGeneric[uuid.UUID]):
    """
    Update model schema with UUID id type.
    """
