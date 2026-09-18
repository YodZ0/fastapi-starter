# CRUDRepository

[`src/core/repositories/crud.py`](../src/core/repositories/crud.py) is a
generic async repository for Postgres. A concrete repository declares its model
and its three schemas; everything else is inherited.

Every method returns a pydantic read schema, never an ORM model. That is the
point of the class: no detached instance and no lazy IO can escape into a layer
that no longer has a session.

## Declaring one

```python
from src.core.repositories import CRUDRepositoryInt


class WidgetRepository(
    CRUDRepositoryInt[
        Widget,
        WidgetReadSchema,
        WidgetCreateSchema,
        WidgetUpdateSchema,
    ]
):
    search_fields = ("name", "description")
```

The base class is `CRUDRepository[Model, Read, Create, Update, Id]` - five
parameters, **identifier last**. Two subclasses pin that last one so the common
case takes four arguments:

| Base | Identifier | Model base |
| --- | --- | --- |
| `CRUDRepositoryInt` | `int` | `BaseInt` |
| `CRUDRepositoryUUID` | `uuid.UUID` | `BaseUUID` |
| `CRUDRepository` | your own | `BaseInt` / `BaseUUID` |

Declaring the generic arguments *is* the implementation - an empty body is a
complete repository. `__init_subclass__` runs at class-creation time and builds
`model`, `read_schemas_mapping`, `create_models_mapping`,
`update_models_mapping` and `model_identities_mapping` from them.

Two details of that mechanism are worth knowing, because they turn mistakes
into errors at import rather than at runtime:

- It reads `cls.__dict__["__orig_bases__"]`, not `getattr`. `__orig_bases__` is
  inherited, so `class WidgetRepository(CRUDRepositoryInt)` with no arguments
  would otherwise read the *base's* type variables and register them as if they
  were a model and its schemas. Written this way, it raises
  `TypeError: WidgetRepository is missing generic type arguments.`
- It slices `[:4]`, which is what lets the full five-argument spelling and the
  pinned `Int`/`UUID` spellings share one implementation.

This is also why ruff `UP046` and `UP047` are in the ignore list in
`pyproject.toml`: rewriting these classes with PEP 695 type parameters would
remove `__orig_bases__` and break the whole scheme.

Instantiating an abstract class - `CRUDRepository`, `CRUDRepositoryInt`,
`CRUDRepositoryUUID`, or any intermediate that sets `__abstract__ = True` in
its own body - raises `TypeError`.

## Construction

```python
def __init__(self, session_manager: SessionManager) -> None: ...
```

One argument. Register the class with `provide(WidgetRepository)` and dishka
supplies the `SessionManager` from `Scope.REQUEST` - see [`docs/di.md`](di.md).

## Reading

```python
async def get(self, obj_id: IdType) -> ReadSchemaType
async def get_or_none(self, obj_id: IdType) -> ReadSchemaType | None
async def get_multi(self, obj_ids: Sequence[IdType], *, strict: bool = False) -> list[ReadSchemaType]
async def get_all(self, *, sorting: Iterable[str] | None = None) -> list[ReadSchemaType]
async def paginate(
    self,
    pagination: PaginationSchema,
    *,
    search: str | None = None,
    search_by: Iterable[str] | None = None,
    sorting: Iterable[str] | None = None,
) -> PaginationResultSchema[ReadSchemaType]
```

- `get` raises `ModelNotFoundError` when the row is absent; `get_or_none`
  swallows exactly that and returns `None`.
- `get_multi` returns a short list when some ids are missing. With
  `strict=True` a missing id raises `ModelNotFoundError` instead. Empty input
  returns `[]` without a query.
- `sorting` takes field names; a leading `-` means DESC. An unknown field
  raises `SortingFieldNotFoundError`.

### Searching

`paginate(search=...)` scans the columns in `search_by`, or `search_fields`
when `search_by` is not given, with a case-insensitive `ILIKE '%term%'` OR-ed
across them.

If neither is set the call raises `SearchFieldNotFoundError`. That is
deliberate: the alternative - matching nothing and returning an empty page - is
a configuration bug that looks like an empty table.

### Filtering

`paginate_with_filter` is `paginate` plus a hook, for the cases where a
repository needs its own WHERE or JOIN but not its own paging and counting:

```python
async def paginate_with_filter(
    self,
    pagination: PaginationSchema,
    *,
    search: str | None = None,
    search_by: Iterable[str] | None = None,
    sorting: Iterable[str] | None = None,
    select_filter: Callable[[sa.Select[...]], sa.Select[...]] | None = None,
) -> PaginationResultSchema[ReadSchemaType]
```

```python
class ActiveWidgetRepository(WidgetRepository):
    async def paginate_active(
        self,
        pagination: PaginationSchema,
    ) -> PaginationResultSchema[WidgetReadSchema]:
        return await self.paginate_with_filter(
            pagination,
            select_filter=lambda query: query.where(Widget.weight > 0),
        )
```

`paginate` simply delegates to it. The count is taken through a subquery
wrapping the filtered select, so it stays correct whatever joins the hook added.

## Writing

```python
async def create(self, create_schema: CreateSchemaType) -> ReadSchemaType
async def bulk_create(self, create_schemas: Sequence[CreateSchemaType]) -> list[ReadSchemaType]
async def update(self, update_schema: UpdateSchemaType) -> ReadSchemaType
async def bulk_update(self, update_schemas: Sequence[UpdateSchemaType]) -> None
async def upsert(self, create_schema: CreateSchemaType) -> ReadSchemaType
async def delete(self, obj_id: IdType, *, strict: bool = False) -> None
async def bulk_delete(self, obj_ids: Sequence[IdType], *, strict: bool = False) -> None
```

Behaviour that is not obvious from the signature:

- **`create`** dumps the schema and **drops `id` when it is `None`**, so the
  server default (`Identity(always=True)` or `gen_random_uuid()`) applies. An
  explicit id is passed through - which works for `BaseUUID` and is rejected by
  Postgres for `BaseInt`, whose key is `GENERATED ALWAYS`.
- **`update`** dumps with `exclude_unset=True`, so only fields the caller
  actually set are written; a field left at its default is not an instruction to
  null the column. The id is required - `ModelIdRequiredError` otherwise.
- **`bulk_create`** returns results in the order they were passed in. Internally
  it groups by model *and* by column set, because a multi-row INSERT renders one
  VALUES clause and every row in a batch must carry the same keys - which stops
  being true as soon as `id` is dropped from some of them.
- **`bulk_update`** returns `None`. Read back explicitly if you need the rows.
- **`upsert`** uses the Postgres dialect directly: `on_conflict_do_update` on
  the primary key, or `on_conflict_do_nothing` when there is nothing to update.
  It needs a known id, so in practice it is a UUID-keyed operation.
- **`delete`** is `bulk_delete([obj_id])`. With `strict=True` an id that matches
  nothing raises `ModelNotFoundError`; by default deleting an absent row is a
  no-op.

Every write wraps SQLAlchemy's `IntegrityError` into `ModelIntegrityError`
carrying the `ModelActionEnum` that was attempted, so a unique-constraint
violation surfaces as a 422 with a readable message rather than a 500.

## Joined-table inheritance

List the children in `__subtypes__` as
`(model, read schema, create schema, update schema)`:

```python
class VehicleRepository(
    CRUDRepositoryInt[
        Vehicle,
        VehicleReadSchema,
        VehicleCreateSchema,
        VehicleUpdateSchema,
    ]
):
    __subtypes__ = (
        (Car, CarReadSchema, CarCreateSchema, CarUpdateSchema),
        (Truck, TruckReadSchema, TruckCreateSchema, TruckUpdateSchema),
    )
```

Reads then load the whole hierarchy with `selectin_polymorphic` and each row
comes back as the read schema registered for its concrete type. Writes dispatch
on the schema type they are handed: `create(CarCreateSchema(...))` inserts into
the parent table and the child table. Deletes walk the chain deepest-first,
because a child row holds a foreign key to its parent.

The models have to cooperate in two ways, both documented in
[`tests/integration/models.py`](../tests/integration/models.py):

- A child redeclares `id` as a plain `ForeignKey` primary key **without**
  `Identity` - the repository fills it in explicitly from the parent INSERT, and
  `GENERATED ALWAYS` would reject exactly that.
- A child inherits *directly* from the parent model. `_get_parent_model` reads
  `__bases__[0]`, so an extra class in between breaks the walk.

The discriminator is carried by the create schema (`kind: str = "car"`) rather
than left to the ORM, because the parent table is written with a Core INSERT
built from that dump, which never sees the child mapper's polymorphic identity.

A model that is loaded but has no read schema registered raises `TypeError`
naming `__subtypes__` as the fix.

## Sessions and transactions

[`src/core/database/session_manager.py`](../src/core/database/session_manager.py)
has two context managers and a clear division of labour:

| Method | Used by | Behaviour |
| --- | --- | --- |
| `get_session()` | repositories | joins the open transaction, or opens its own |
| `transaction()` | use cases | commits on exit, rolls back on error, no-op if one is already open |

Both are re-entrant, and that is what makes the two levels compose. Every
repository method already opens `get_session()`, so on its own each call is its
own transaction. Wrap several in a use case and they become one:

```python
async with self._session_manager.transaction():
    widget = await self._widget_repo.create(create_schema)
    await self._audit_repo.create(AuditCreateSchema(widget_id=widget.id))
```

If the second call raises, the first is rolled back. Without the wrapper the
first would already have been committed.

Both also issue `SET CONSTRAINTS ALL IMMEDIATE` when they open a transaction,
so deferred constraints fail at the statement that violated them rather than at
commit. Pass `immediate=False` to skip it when a batch legitimately needs to
pass through an inconsistent intermediate state.

The session itself is `Scope.REQUEST` and is created with `autoflush=False` and
`expire_on_commit=False` - see [`docs/di.md`](di.md).

## Errors

| Raised by | Exception | HTTP |
| --- | --- | --- |
| `get`, `get_multi(strict=True)`, `bulk_delete(strict=True)` | `ModelNotFoundError` | 404 |
| any write, on constraint violation | `ModelIntegrityError` | 422 |
| `update`, `bulk_update` without an id | `ModelIdRequiredError` | 400 |
| `sorting` with an unknown field | `SortingFieldNotFoundError` | 400 |
| `search` with no `search_fields` / `search_by` | `SearchFieldNotFoundError` | 400 |

All five are registered in `src/handlers/handlers.py`, so a service may simply
let them propagate - see [`docs/architecture.md`](architecture.md#errors).

## The executable specification

`tests/integration/core/repositories/` covers this class against a real
Postgres started by testcontainers:

| File | Covers |
| --- | --- |
| `test_crud_read.py` | `get`, `get_or_none`, `get_multi`, `get_all` |
| `test_crud_write.py` | `create`, `update`, `upsert`, `delete` and their bulk forms |
| `test_crud_pagination.py` | `paginate`, search, sorting, `select_filter` |
| `test_crud_polymorphic.py` | `__subtypes__` across `Vehicle` / `Car` / `Truck` |

When this page and those tests disagree, the tests are right.
