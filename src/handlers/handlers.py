from fastapi import FastAPI

from src.core.exceptions import (
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
    SearchFieldNotFoundError,
    SortingFieldNotFoundError,
)
from src.handlers.http_error_handler import (
    internal_server_error_handler,
    model_id_required_error_handler,
    model_integrity_error_handler,
    model_not_found_error_handler,
    search_field_not_found_error_handler,
    sorting_field_not_found_error_handler,
)


def apply_exception_handlers(app: FastAPI) -> None:
    """
    Applies application exception handlers.
    """
    app.exception_handler(SearchFieldNotFoundError)(
        search_field_not_found_error_handler
    )
    app.exception_handler(SortingFieldNotFoundError)(
        sorting_field_not_found_error_handler
    )
    app.exception_handler(ModelNotFoundError)(model_not_found_error_handler)
    app.exception_handler(ModelIdRequiredError)(model_id_required_error_handler)
    app.exception_handler(ModelIntegrityError)(model_integrity_error_handler)
    app.exception_handler(Exception)(internal_server_error_handler)
