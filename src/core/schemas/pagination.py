from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

from src.core.database.type_vars import ModelType

TReadSchema = TypeVar("TReadSchema")


class PaginationResultSchema(BaseModel, Generic[TReadSchema]):
    objects: list[TReadSchema]
    count: int


class PaginationSchema(BaseModel):
    limit: int
    offset: int


@dataclass(frozen=True)
class PaginationModelResult(Generic[ModelType]):
    # Sequence, not list: this holds the result of `.scalars().all()`, which is
    # typed as a Sequence. Callers only read the set and map it into schemas, so
    # narrowing to list bought nothing and forced a copy on every call.
    objects: Sequence[ModelType]
    count: int
