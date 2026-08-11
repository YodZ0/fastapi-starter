from typing import Annotated

from fastapi import Depends, Query

from src.core.schemas import PaginationSchema


def pagination_query(
    limit: int = Query(10, ge=1, le=100, description="Query limit."),
    offset: int = Query(0, ge=0, description="Query offset."),
) -> PaginationSchema:
    """
    Pagination query dependency.
    """
    return PaginationSchema(limit=limit, offset=offset)


Pagination = Annotated[PaginationSchema, Depends(pagination_query)]
