from fastapi import APIRouter
from src.settings import settings


router_v1 = APIRouter(prefix=settings.api.v1.prefix)
# Include API routers
# router_v1.include_router()
