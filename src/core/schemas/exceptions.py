from pydantic import BaseModel


class BusinessLogicExceptionSchema(BaseModel):
    """
    Business-logic base exception schema.
    """

    type: str
    msg: str
    traceback: str | None


class ModelAlreadyExistsErrorSchema(BusinessLogicExceptionSchema):
    """
    The error scheme that occurs when attempting to create a model with an existing unique field.
    """

    field: str
    value: str
