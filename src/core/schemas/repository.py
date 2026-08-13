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

    # Optional on purpose: the identifier is normally assigned by the database,
    # but `upsert` and seeding both need a way to pass an explicit one. The
    # repository drops the key from the INSERT when it is left as None.
    id: IdType | None = None


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
