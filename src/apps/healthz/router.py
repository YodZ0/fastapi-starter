from fastapi import APIRouter, status

from src.core.schemas import StatusOKResponseSchema

__all__ = ("router",)

router = APIRouter(
    prefix="/healthz",
    tags=["Health"],
)


@router.get("", status_code=status.HTTP_200_OK)
async def check_api_health() -> StatusOKResponseSchema:
    return StatusOKResponseSchema()
