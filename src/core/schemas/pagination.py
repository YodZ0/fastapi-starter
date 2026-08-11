from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

from src.core.models.type_vars import ModelType

TReadSchema = TypeVar("TReadSchema")


class PaginationResultSchema(BaseModel, Generic[TReadSchema]):
    objects: list[TReadSchema]
    count: int


class PaginationSchema(BaseModel):
    limit: int
    offset: int


@dataclass(frozen=True)
class PaginationModelResult(Generic[ModelType]):
    # Sequence, а не list: сюда кладут результат `.scalars().all()`, а он по
    # типу именно Sequence. Наружу набор только читают и перекладывают в схемы,
    # так что сужение до list ничего не давало и требовало копии на каждом
    # вызове.
    objects: Sequence[ModelType]
    count: int
