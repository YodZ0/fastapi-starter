from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class RequestSchema(BaseModel):
    """
    Request API schema.
    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
        )
    )


class ResponseSchema(BaseModel):
    """
    Response API schema.
    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
        )
    )


class StatusOKResponseSchema(ResponseSchema):
    """
    Status OK schema.
    """

    status: str = "OK"
