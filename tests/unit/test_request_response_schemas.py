"""
Модуль, содержащий тесты валидации/сериализации DTO схем
"""

from src.core.schemas import (
    RequestSchema,
    ResponseSchema,
    ReadSchemaInt,
    CreateSchemaInt,
)


class ObjectCreateSchema(RequestSchema, CreateSchemaInt):
    value: int
    some_text_field: str


class ObjectReadSchema(ResponseSchema, ReadSchemaInt):
    value: int
    some_text_field: str


def test_request_schema_validation():
    """
    Проверяем, что срабатывает валидация camelCase в snake_case.
    """
    request_create_schema = {"value": 1, "someTextField": "test"}
    create_dto = ObjectCreateSchema.model_validate(request_create_schema)
    assert create_dto.some_text_field == "test"


def test_response_schema_serialization():
    """
    Проверяем, что срабатывает сериализация snake_case в camelCase.
    """
    data = {
        "id": 1,
        "value": 1,
        "some_text_field": "test",
    }
    read_schema = ObjectReadSchema(**data)
    # Используем by_alias=True для сериализации на выходе
    assert read_schema.model_dump(by_alias=True) == {
        "id": 1,
        "value": 1,
        "someTextField": "test",
    }


def test_request_to_response_transformation():
    """
    Проверяем весь процесс от валидации до сериализации.
    """
    request_create_schema = {"value": 1, "someTextField": "test"}
    create_dto = ObjectCreateSchema.model_validate(request_create_schema)
    # Добавляем значение для пустого поля
    create_dto.id = 1
    # Изменяем существующее поле
    create_dto.some_text_field = "new text"
    read_schema = ObjectReadSchema(**create_dto.model_dump())
    # Используем by_alias=True для сериализации на выходе
    assert read_schema.model_dump(by_alias=True) == {
        "id": 1,
        "value": 1,
        "someTextField": "new text",
    }
