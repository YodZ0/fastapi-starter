"""
HTTP exception handlers.
"""

import logging

from fastapi import HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler

from src.core.exceptions import (
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
    SearchFieldNotFoundError,
    SortingFieldNotFoundError,
)
from src.settings import settings

logger = logging.getLogger(__name__)

# --- Unhandled ---


async def internal_server_error_handler(
    request: Request,
    error: Exception,
) -> Response:
    """
    Handler for unexpected errors.
    """
    logger.error("Unexpected error occurred!", exc_info=error)
    detail = "Unexpected server error."
    if settings.debug:
        detail += f" Error: {error}"
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        ),
    )


# --- Repository ---


async def model_not_found_error_handler(
    request: Request,
    error: ModelNotFoundError,
) -> Response:
    """
    Handler for the error raised when a model could not be found.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error.get_schema(settings.debug).model_dump(),
        ),
    )


async def model_integrity_error_handler(
    request: Request,
    error: ModelIntegrityError,
) -> Response:
    """
    Handler for errors raised while creating/updating/deleting a model.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=error.get_schema(settings.debug).model_dump(),
        ),
    )


async def model_id_required_error_handler(
    request: Request,
    error: ModelIdRequiredError,
) -> Response:
    """
    Handler for errors raised if model ID is required.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.get_schema(settings.debug).model_dump(),
        ),
    )


async def sorting_field_not_found_error_handler(
    request: Request,
    error: SortingFieldNotFoundError,
) -> Response:
    """
    Handler for attempts to sort by a field the model does not have.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.get_schema(settings.debug).model_dump(),
        ),
    )


async def search_field_not_found_error_handler(
    request: Request,
    error: SearchFieldNotFoundError,
) -> Response:
    """
    Handler for attempts to search by a field the model does not have.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.get_schema(settings.debug).model_dump(),
        ),
    )
