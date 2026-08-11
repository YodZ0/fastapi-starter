import uuid
from typing import TypeVar

IdType = TypeVar("IdType", bound=int | uuid.UUID | str)
type IntIDType = int
type UUIDType = uuid.UUID
