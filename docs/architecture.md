# Architecture

How a request becomes a response, and what is assembled where.

## Layers

A feature is split across six layers. Each one knows only about the layer
directly beneath it:

| Layer | Lives in | Depends on | Returns |
| --- | --- | --- | --- |
| Model | `models/` | SQLAlchemy only | ORM instances |
| Schema | `schemas/` | pydantic only | - (it *is* the DTO) |
| Repository | `repositories/` | `SessionManager`, models, schemas | read schemas |
| Service | `services/` | one repository | read schemas |
| Use case | `use_cases/` | one or more services | read schemas |
| Router | `router.py` | use cases | response schema |

The rule that holds the whole thing together is stated in the module docstring
of [`src/core/repositories/crud.py`](../src/core/repositories/crud.py):

> Every method returns a Pydantic read schema rather than an ORM model, so no
> detached instance - and no lazy IO - escapes the repository.

That is why a service never receives a model and a router never receives
anything it cannot serialise. The session is closed when the request scope
ends; an ORM instance that outlived it would raise on the first unloaded
attribute, at a point in the code that has no way to reconnect.

[`docs/domain.md`](domain.md) documents what goes in each layer.

## Assembly

`create_app()` in [`src/bootstrap.py`](../src/bootstrap.py) applies four things,
in this order:

```python
app = FastAPI(...)
app = apply_middleware(app)          # src/middleware.py
app = apply_routes(app)              # src/router.py
apply_exception_handlers(app)        # src/handlers/handlers.py
container = setup_async_container()  # src/di.py
setup_dishka(container, app)
```

`setup_dishka` is last because it is what puts the container on
`app.state.dishka_container`, and the lifespan reads it from there.

The lifespan resolves `RedisCache` and pings it before the application accepts
traffic, so a misconfigured cache fails the deploy instead of failing the first
request that needs it. Both halves of its error handling are deliberate:
Starlette never runs the shutdown half of a lifespan whose startup raised, so
the abort path has to close the container itself, and the normal path closes it
in a `finally` because a generator torn down by `GeneratorExit` would otherwise
skip the close and leak the pools.

`setup_logging(settings.base_dir)` runs at *import* time of `src.bootstrap`,
before `create_app` is ever called, so that anything logged during startup is
already formatted.

## Routing

Prefixes are composed, never written out in full:

```text
src/router.py        settings.api.prefix      "/api"
  src/api/v1.py      settings.api.v1.prefix   "/v1"
    domain router    prefix="/widgets"        "/widgets"
```

giving `GET /api/v1/widgets`. Because the first two come from settings, tests
derive paths the same way rather than hardcoding them:

```python
WIDGETS_PATH = f"{settings.api.prefix}{settings.api.v1.prefix}/widgets"
```

## Middleware

`apply_middleware` adds three, and the docstring carries the warning that
matters: **the last middleware added is called first.** The effective order is
CORS, then `calc_process_time` (sets `X-Process-Time`), then
`request_id_middleware` (sets `X-Request-ID`).

## Request context

[`src/core/context.py`](../src/core/context.py) is a `ContextVar` and three
functions:

```python
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

def get_request_id() -> str: ...
def set_request_id(request_id: str) -> Token[str]: ...
def reset_request_id(token: Token[str]) -> None: ...
```

It exists so that a log line written five layers deep can be traced back to the
request that caused it, without threading a request id through every function
signature.

There are exactly two participants. `request_id_middleware` takes the incoming
`X-Request-ID` header or mints a `uuid4().hex`, sets it, echoes it back on the
response, and resets the token in a `finally`:

```python
request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
token = set_request_id(request_id)
try:
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
finally:
    reset_request_id(token)
```

And `RequestIdFilter` in [`src/logs.py`](../src/logs.py) copies the value onto
every record:

```python
class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
```

The filter is attached to *handlers* rather than loggers in `.logging.yaml`, so
it applies to everything that reaches an output regardless of which logger
emitted it, and both formatters print `%(request_id)s`.

The `"-"` default is the reason nothing else needs a guard: CLI commands,
startup and background tasks run outside any request and simply log a dash.

To add another context var - a tenant id, a correlation id - follow the same
shape: a module-level `ContextVar` with a safe default, a setter that returns
the token, a reset that is always called from a `finally`. Resetting with the
token rather than setting the default back is what keeps concurrent requests
from reading each other's values.

## Errors

Domain errors subclass `BusinessLogicException`
([`src/core/exceptions/business_error.py`](../src/core/exceptions/business_error.py)),
an ABC with one abstract member:

```python
@property
def type(self) -> str:
    return to_snake(type(self).__name__.removesuffix("Error"))

@property
@abstractmethod
def msg(self) -> str: ...

def get_schema(self, debug: bool) -> BusinessLogicExceptionSchema: ...
```

`type` is derived from the class name, which is why domain errors are named
`...Error`: `ModelNotFoundError` becomes `"model_not_found"` on the wire. A
class named `...Exception` would ship the suffix to the client.

`get_schema(debug)` builds the response body and includes the traceback only
when `settings.debug` is on.

`apply_exception_handlers` registers the mapping, and
[`src/handlers/http_error_handler.py`](../src/handlers/http_error_handler.py)
turns each one into a status:

| Exception | Status |
| --- | --- |
| `ModelNotFoundError` | 404 |
| `ModelIntegrityError` | 422 |
| `ModelIdRequiredError` | 400 |
| `SortingFieldNotFoundError` | 400 |
| `SearchFieldNotFoundError` | 400 |
| `Exception` | 500 |

The `Exception` entry is a catch-all, so an unregistered domain error is
answered with a 500 and a generic message. Registering it is a step in
[adding a domain](domain.md#3-handlers).

## Settings

[`src/settings.py`](../src/settings.py) is pydantic-settings with
`env_nested_delimiter="__"`, so a nested field is spelled `SECTION__FIELD` in
the environment: `DB__POOL_SIZE`, `REDIS__KEY_PREFIX`, `APP__TITLE`. Every
variable is listed with a comment in `.env.template`.

`settings = Settings()` is a module-level singleton built at import time.
`CoreProvider.get_settings` returns *that object* rather than constructing a
fresh one - a second instance would re-parse `.env` and leave the container
holding a config that is not the one the rest of the code imported.
