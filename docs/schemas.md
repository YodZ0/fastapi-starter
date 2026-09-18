# Schemas

There are two families of pydantic models in `src/core/schemas/`, and they are
not interchangeable:

- **Repository schemas** - the Read / Create / Update triad a repository is
  parameterised with. Snake-case, `from_attributes` enabled.
- **API schemas** - `RequestResponseSchema`, for routes whose wire contract is
  camelCase.

A route may return a read schema directly, which is what the template does by
default. Reach for the API family when the contract has to differ from the
Python one.

## BaseSchema

Every repository schema descends from
[`src/core/schemas/repository.py`](../src/core/schemas/repository.py):

```python
class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,      # validates schema from class attributes
        validate_by_name=True,     # allows to create schema with aliases its attribute
        validate_assignment=True,  # validates types if schema already created
    )
```

`from_attributes=True` is the load-bearing one: it is what lets
`CRUDRepository.model_validate` turn an ORM row into a read schema, which is
how models are kept from escaping the repository.

`validate_assignment=True` means mutating a schema after construction is
type-checked too, so a field assigned the wrong type fails there rather than at
serialisation.

## The Read / Create / Update triad

Three generics, each contributing only `id`, plus pinned `Int` and `UUID`
leaves:

| Generic | Int leaf | UUID leaf | `id` |
| --- | --- | --- | --- |
| `ReadSchemaGeneric[IdType]` | `ReadSchemaInt` | `ReadSchemaUUID` | required |
| `CreateSchemaGeneric[IdType]` | `CreateSchemaInt` | `CreateSchemaUUID` | `None` by default |
| `UpdateSchemaGeneric[IdType]` | `UpdateSchemaInt` | `UpdateSchemaUUID` | `None` by default |

`id` is optional on **create** because the database normally assigns it - but
`upsert` and seeding both need a way to pass an explicit one, so the field
exists and the repository drops the key from the INSERT when it is left as
`None`.

`id` is optional on **update** because `bulk_update` needs the field to be
declarable; a call that actually omits it raises `ModelIdRequiredError`.

Subclass the leaf that matches your model's base - `ReadSchemaInt` for a
`BaseInt` model, `ReadSchemaUUID` for `BaseUUID`:

```python
class WidgetReadSchema(ReadSchemaInt):
    name: str
    slug: str
    weight: int
    description: str | None
    created_at: datetime
    updated_at: datetime


class WidgetCreateSchema(CreateSchemaInt):
    name: str
    slug: str
    weight: int
    description: str | None = None


class WidgetUpdateSchema(UpdateSchemaInt):
    name: str | None = None
    slug: str | None = None
    weight: int | None = None
    description: str | None = None
```

Read fields mirror the columns, including the ones the database fills in.
Create fields are required where the column is. **Every update field defaults
to `None`**, because `update` dumps with `exclude_unset=True`: a field the
caller never mentioned is left alone, and only an explicitly-passed `None`
nulls a column.

## List projections

A list endpoint that should not ship every column gets a projection inheriting
from the read schema:

```python
class WidgetListReadSchema(WidgetReadSchema):
    """
    Trimmed projection for the list endpoint.
    """
```

Inheritance rather than a parallel class keeps the two from drifting, and the
conversion is a re-wrap in the use case:

```python
return PaginationResultSchema(objects=result.objects, count=result.count)
```

To actually drop fields, redeclare the projection against `ReadSchemaInt` and
list only what the endpoint returns. Either way the name stays
`{Entity}ListReadSchema`.

## Pagination

From [`src/core/schemas/pagination.py`](../src/core/schemas/pagination.py):

```python
class PaginationSchema(BaseModel):
    limit: int
    offset: int


class PaginationResultSchema(BaseModel, Generic[TReadSchema]):
    objects: list[TReadSchema]
    count: int
```

`count` is the total number of matching rows, not the length of `objects`.

Routes do not build `PaginationSchema` by hand - they take the `Pagination`
alias from [`src/core/depends.py`](../src/core/depends.py):

```python
def pagination_query(
    limit: int = Query(10, ge=1, le=100, description="Query limit."),
    offset: int = Query(0, ge=0, description="Query offset."),
) -> PaginationSchema:
    return PaginationSchema(limit=limit, offset=offset)


Pagination = Annotated[PaginationSchema, Depends(pagination_query)]
```

The bounds live there, so `?limit=100000` is rejected by FastAPI before any
layer sees it. Use it as a plain parameter:

```python
async def view_all(
    use_case: FromDishka[ViewAllUseCase],
    pagination: Pagination,
) -> PaginationResultSchema[WidgetListReadSchema]: ...
```

`PaginationModelResult` is the same shape over ORM models instead of schemas,
for code that pages before mapping. Nothing in `src/` uses it today.

## API request and response schemas

For a camelCase wire contract, from
[`src/core/schemas/request_response.py`](../src/core/schemas/request_response.py):

```python
class RequestResponseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
        validate_by_name=True,
    )
```

Fields stay snake_case in Python and are read and written as camelCase:
`created_at` serialises to `createdAt`. `validate_by_name=True` means both
spellings are accepted on input, which is what keeps tests able to construct
instances with the Python names.

`StatusOKResponseSchema` is the ready-made envelope used by the health check:

```python
class StatusOKResponseSchema(RequestResponseSchema):
    status: str = "OK"
    details: dict[str, Any] | None = None
```

Note that this family does **not** set `from_attributes`, so it cannot be
validated straight off an ORM object - which is correct, since it sits on the
far side of the repository boundary.

## Error responses

[`src/core/schemas/exceptions.py`](../src/core/schemas/exceptions.py) is the
body every handled error returns:

```python
class BusinessLogicExceptionSchema(BaseModel):
    type: str
    msg: str
    traceback: str | None
```

`type` is the machine-readable discriminator derived from the exception class
name, `msg` is the human sentence from the exception's `msg` property, and
`traceback` is populated only when `settings.debug` is on.
`ModelAlreadyExistsErrorSchema` extends it with `field` and `value`.

See [`docs/architecture.md`](architecture.md#errors) for how exceptions reach
these schemas and which status each one gets.
