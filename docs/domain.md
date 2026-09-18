# Domains

A feature lives in `src/apps/{domain}/`. This page covers what goes inside one
and how to attach it to the application.

The worked example below is `widgets`. It is not invented: `Widget`, its three
schemas and `WidgetRepository` exist in
[`tests/integration/models.py`](../tests/integration/models.py) and
[`tests/integration/repositories.py`](../tests/integration/repositories.py),
where the integration suite exercises them against a real Postgres. Read those
two files alongside this one - they are the same code, running.

## Layout

```text
src/apps/{domain}/
├── __init__.py
├── router.py          # APIRouter; depends on use cases only
├── provider.py        # dishka Provider for this domain
├── depends.py         # Annotated[...] FastAPI dependency aliases
├── exceptions.py      # BusinessLogicException subclasses
├── interfaces.py      # optional: Protocols other domains may depend on
├── models/            # SQLAlchemy models
├── schemas/           # pydantic Read / Create / Update / ListRead
├── repositories/      # CRUDRepository subclasses
├── services/          # business logic over one repository
└── use_cases/         # orchestration; one module per action
```

Layer packages are plural, single-module layers at the root are singular. A
module inside a layer package is named after the entity (`widget.py`) - except
in `use_cases/`, which is named after the action (`view_all.py`), because that
is what a use case is.

Every package `__init__.py` re-exports with the redundant-alias form:

```python
"""
Widget repositories.
"""

from .widget import WidgetRepository as WidgetRepository
```

The `as` is not noise. mypy runs with `strict = true`, which implies
`no_implicit_reexport`; without the alias the name is private to the module and
importing it from the package is an error.

### models/

Pick a base by identifier type. Both come from
[`src/core/database/base_model.py`](../src/core/database/base_model.py):

- `BaseInt` - `BigInteger` with `Identity(always=True)`.
- `BaseUUID` - `UUID` with a `gen_random_uuid()` server default.

`TimestampMixin` adds `created_at` and `updated_at`.

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.base_model import BaseInt
from src.core.database.mixins import TimestampMixin


class Widget(BaseInt, TimestampMixin):
    __tablename__ = "widgets"

    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    weight: Mapped[int]
    description: Mapped[str | None] = mapped_column(String(256), default=None)
```

The choice has consequences further up. `BaseInt.id` is `GENERATED ALWAYS`, so
Postgres rejects an INSERT that names it - which means a client cannot choose
the id, and `upsert` has nothing to conflict on. A UUID key can be generated
before the row exists, so client-chosen identifiers and `upsert` both work.
Prefer `BaseUUID` when ids are exposed to clients or created outside the
database; prefer `BaseInt` for dense internal tables.

`Base` also gives every model a `__repr__` driven by `repr_cols_num` (how many
leading columns to show, default 1) and `repr_cols` (extra ones by name).

### schemas/

Three schemas per entity, matching the repository's generic arguments, plus a
projection for list endpoints:

```python
from datetime import datetime

from src.core.schemas import CreateSchemaInt, ReadSchemaInt, UpdateSchemaInt


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


class WidgetListReadSchema(WidgetReadSchema):
    """
    Trimmed projection for the list endpoint.
    """
```

Update fields all default to `None` so that `model_dump(exclude_unset=True)` in
`CRUDRepository.update` writes only what the caller actually set. The list
schema inherits from the read schema: it is the same rows, narrowed.

Full reference: [`docs/schemas.md`](schemas.md).

### repositories/

```python
from src.apps.widgets.models import Widget
from src.apps.widgets.schemas import (
    WidgetCreateSchema,
    WidgetReadSchema,
    WidgetUpdateSchema,
)
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

Declaring the generic arguments *is* the implementation. `__init_subclass__`
reads them back at class-creation time and builds the model and schema
mappings, so an empty body is a complete repository. `search_fields` and
`__subtypes__` are the only two knobs.

Full reference: [`docs/repository.md`](repository.md).

### services/

A service owns one entity and the rules that apply to it. Collaborators arrive
through `__init__` and are stored on a private attribute:

```python
from src.apps.widgets.repositories import WidgetRepository
from src.apps.widgets.schemas import WidgetReadSchema
from src.core.schemas import PaginationResultSchema, PaginationSchema


class WidgetService:
    def __init__(self, repo: WidgetRepository) -> None:
        self._repo = repo

    async def get_all(
        self,
        pagination: PaginationSchema,
    ) -> PaginationResultSchema[WidgetReadSchema]:
        return await self._repo.paginate(pagination)
```

Nothing is constructed here - dishka reads those `__init__` annotations and
supplies the repository. See [`docs/di.md`](di.md).

### use_cases/

A use case orchestrates. It is where several services are combined, where a
cross-domain call happens, and where a transaction boundary is drawn.

The shape is a template method: `execute()` is the only public entry point and
runs a fixed three-step skeleton, so every use case has the same place to hang
validation, auditing or event publishing.

```python
from src.apps.widgets.schemas import WidgetListReadSchema
from src.apps.widgets.services import WidgetService
from src.core.schemas import PaginationResultSchema, PaginationSchema


class ViewAllUseCase:
    """
    Read all records use case.
    """

    def __init__(self, widget_service: WidgetService) -> None:
        self._widget_service = widget_service

    async def execute(
        self,
        pagination: PaginationSchema,
    ) -> PaginationResultSchema[WidgetListReadSchema]:
        await self._before_execute()
        result = await self._execute(pagination=pagination)
        await self._after_execute()
        return result

    async def _execute(
        self,
        pagination: PaginationSchema,
    ) -> PaginationResultSchema[WidgetListReadSchema]:
        result = await self._widget_service.get_all(pagination)
        return PaginationResultSchema(objects=result.objects, count=result.count)

    async def _before_execute(self) -> None:
        pass

    async def _after_execute(self) -> None:
        pass
```

A use case that writes through more than one repository wraps them so that they
commit or roll back together. `SessionManager.transaction()` is re-entrant, and
the `get_session()` calls the repositories make inside it join the open
transaction instead of committing on their own:

```python
class TransferUseCase:
    def __init__(
        self,
        session_manager: SessionManager,
        widget_service: WidgetService,
        crate_service: CrateService,
    ) -> None:
        self._session_manager = session_manager
        self._widget_service = widget_service
        self._crate_service = crate_service

    async def _execute(self, widget_id: int, crate_id: int) -> None:
        async with self._session_manager.transaction():
            await self._widget_service.detach(widget_id)
            await self._crate_service.attach(crate_id, widget_id)
```

The contract is documented in
[`docs/repository.md`](repository.md#sessions-and-transactions).

### router.py

```python
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, status

from src.core.depends import Pagination
from src.core.schemas import PaginationResultSchema

from .depends import WidgetIdPath
from .schemas import WidgetListReadSchema
from .use_cases import ViewAllUseCase

__all__ = ("router",)

router = APIRouter(
    prefix="/widgets",
    tags=["Widgets"],
)


@router.get("", status_code=status.HTTP_200_OK)
@inject
async def view_all(
    use_case: FromDishka[ViewAllUseCase],
    pagination: Pagination,
) -> PaginationResultSchema[WidgetListReadSchema]:
    """
    Read all data with pagination.
    """
    return await use_case.execute(pagination=pagination)
```

Points worth copying exactly:

- The router object is always named `router` and re-exported through
  `__all__ = ("router",)`; `src/api/v1.py` imports it by that name.
- The prefix is the plural resource, the tag is the capitalised plural. The
  `/api/v1` part is added upstream - never write it here.
- `@inject` goes *below* the route decorator, on any handler that resolves
  something from the container.
- `FromDishka[...]` is the container; `Pagination` and other `Annotated`
  aliases are ordinary FastAPI dependencies. They mix freely.
- The return annotation is the response model. FastAPI validates against it.

**A router depends on use cases and nothing else.** Injecting a service or a
repository directly skips the layer where transactions and orchestration live,
and the shortcut is invisible at the call site once it exists.

### depends.py

FastAPI dependency aliases, named `{Thing}{Source}`:

```python
"""
Widget domain FastAPI dependencies.
"""

from typing import Annotated

from fastapi import Path

from src.core.type_vars import UUIDType

WidgetIdPath = Annotated[
    UUIDType,
    Path(description="Widget model ID."),
]
```

The same pattern produces the shared `Pagination` in
[`src/core/depends.py`](../src/core/depends.py) - put an alias here when it is
specific to this domain, in core when every domain wants it.

### exceptions.py

```python
"""
Widget domain exceptions.
"""

from src.core.exceptions import BusinessLogicException

__all__ = ("WidgetLockedError",)


class WidgetLockedError(BusinessLogicException):
    """
    Raised when a widget is modified while another operation holds it.
    """

    def __init__(
        self,
        model_id: int,
        *args: object,
        message: str | None = None,
    ) -> None:
        super().__init__(*args)
        self.model_id = model_id
        self.message = message

    @property
    def msg(self) -> str:
        msg = f"Widget(id={self.model_id}) is locked."
        if self.message is not None:
            msg += f" {self.message}"
        return msg
```

Store the context in `__init__`, build the sentence in `msg`. End the class
name in `Error`: `BusinessLogicException.type` strips exactly that suffix to
produce the machine-readable `type` field, so `WidgetLockedError` ships as
`"widget_locked"`.

Defining the error is half the work - it answers 500 until it is registered.
See [handlers](#3-handlers).

### interfaces.py

Domains talk to each other through `Protocol`s, never by importing another
concrete service. The owning domain publishes the interface:

```python
# src/apps/widgets/interfaces.py
from typing import Protocol

from src.apps.widgets.schemas import WidgetReadSchema


class WidgetLookupProtocol(Protocol):
    async def get(self, widget_id: int) -> WidgetReadSchema: ...
```

binds its implementation to it in its own provider:

```python
# src/apps/widgets/provider.py
widget_service = provide(WidgetService, provides=WidgetLookupProtocol)
```

and the consumer depends on the protocol:

```python
# src/apps/crates/use_cases/pack.py
from src.apps.widgets.interfaces import WidgetLookupProtocol


class PackUseCase:
    def __init__(self, widgets: WidgetLookupProtocol) -> None:
        self._widgets = widgets
```

The import still crosses a domain boundary, but it crosses to a declaration
rather than to an implementation: the consumer cannot reach the other domain's
repository, and the two can be tested apart.

## Naming

| Kind | Pattern | Example |
| --- | --- | --- |
| Model | `{Entity}` | `Widget` |
| Read schema | `{Entity}ReadSchema` | `WidgetReadSchema` |
| Create schema | `{Entity}CreateSchema` | `WidgetCreateSchema` |
| Update schema | `{Entity}UpdateSchema` | `WidgetUpdateSchema` |
| List projection | `{Entity}ListReadSchema` | `WidgetListReadSchema` |
| Repository | `{Entity}Repository` | `WidgetRepository` |
| Service | `{Entity}Service` | `WidgetService` |
| Use case | `{Action}UseCase` | `ViewAllUseCase` |
| Provider | `{Domain}Provider` | `WidgetProvider` |
| Domain error | `{Something}Error` | `WidgetLockedError` |
| Cross-domain interface | `{Name}Protocol` | `WidgetLookupProtocol` |
| Dependency alias | `{Thing}{Source}` | `WidgetIdPath` |
| Enum | `{Name}Enum` | `ModelActionEnum` |
| Type alias | `{Name}Type` | `UUIDType` |

Handlers are named for the action without the entity (`view_all`, `get_one`),
since the router prefix already says which entity. `__all__` is a tuple.
Imports are relative between modules at the domain root and absolute
(`src.apps.widgets....`) from inside a layer package.

---

## Connecting a domain to the application

Nothing is discovered automatically. A new domain is attached by hand, in these
five places.

### 1. api

[`src/api/v1.py`](../src/api/v1.py) - import the router under an aliased name
and include it:

```python
from src.apps.widgets.router import router as widgets_router

router_v1 = APIRouter(prefix=settings.api.v1.prefix)
router_v1.include_router(widgets_router)
```

The route is now served at `/api/v1/widgets`, composed from
`settings.api.prefix`, `settings.api.v1.prefix` and the router's own prefix. A
future `/v2` gets its own module next to `v1.py` and its own line in
`src/router.py`.

### 2. di

[`src/di.py`](../src/di.py) - import the provider and register it under the
`# Apps providers` comment:

```python
from src.apps.widgets.provider import WidgetProvider


def setup_async_container(*extra_providers: Provider) -> AsyncContainer:
    return make_async_container(
        # Core providers
        FastapiProvider(),
        CoreProvider(),
        # Apps providers
        WidgetProvider(),
        *extra_providers,
    )
```

The position matters: `*extra_providers` stays last so that a test provider
registered with `override=True` wins over the real one. Adding a domain
provider after it would silently defeat every override in the suite.

Writing the provider itself: [`docs/di.md`](di.md).

### 3. handlers

Only needed when the domain defines its own exceptions. Without this step the
`Exception` catch-all answers 500.

Add a handler to
[`src/handlers/http_error_handler.py`](../src/handlers/http_error_handler.py),
following the existing shape:

```python
async def widget_locked_error_handler(
    request: Request,
    error: WidgetLockedError,
) -> Response:
    """
    Handler for the error raised when a widget is locked.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error.get_schema(settings.debug).model_dump(),
        ),
    )
```

The second parameter is annotated with the concrete exception type, and
`error.get_schema(settings.debug).model_dump()` is the body - that pair is what
makes the response shape identical to every other handled error.

and register it in [`src/handlers/handlers.py`](../src/handlers/handlers.py):

```python
app.exception_handler(WidgetLockedError)(widget_locked_error_handler)
```

Register more specific exceptions before more general ones; the `Exception`
entry stays at the bottom.

### 4. migrations

A new model needs a revision:

```sh
docker compose run --rm backend alembic revision --autogenerate -m "add widgets"
docker compose up
```

[`alembic/env.py`](../alembic/env.py) uses `target_metadata = Base.metadata`,
so autogenerate only sees a model whose module has been imported. Re-exporting
it through `src/apps/{domain}/models/__init__.py` and having the repository
import it is normally enough; a model that nothing imports yet produces an
empty revision.

Always read the generated file before applying it.

### 5. tests

HTTP-level tests go in `tests/unit/apps/{domain}/` and follow
[`tests/unit/apps/test_healthz.py`](../tests/unit/apps/test_healthz.py):

```python
@pytest.fixture
async def app():
    app = create_app()
    yield app
    await app.state.dishka_container.close()


@pytest.fixture
async def client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

`httpx.ASGITransport` does not run the ASGI lifespan, so these tests need
neither Postgres nor Redis and stay in the Docker-free commit gate. Override
whatever would otherwise reach out, using the `override=True` recipe in
[`docs/di.md`](di.md#overriding-a-dependency-in-tests).

Repository tests that need a real database go under `tests/integration/`, where
the `integration` marker is applied automatically and every test runs inside a
transaction that is rolled back afterwards.
