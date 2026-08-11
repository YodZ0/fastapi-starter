from typing import Any

from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class RequestResponseSchema(BaseModel):
    """
    Request/Response API schema.

    Converts camelCase into snake_case and vice versa.
    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
        validate_by_name=True,
    )


class StatusOKResponseSchema(RequestResponseSchema):
    """
    Status OK response schema.
    """

    status: str = "OK"
    details: dict[str, Any] | None = None
