from typing import TypeVar

from src.core.database.base_model import Base, BaseInt, BaseUUID

ModelType = TypeVar("ModelType", bound=Base | BaseInt | BaseUUID)
ModelWithIdType = TypeVar("ModelWithIdType", bound=BaseInt | BaseUUID)
ModelIntType = TypeVar("ModelIntType", bound=BaseInt)
ModelUUIDType = TypeVar("ModelUUIDType", bound=BaseUUID)
