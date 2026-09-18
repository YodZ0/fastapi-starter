# Dependency injection

The container is [dishka](https://github.com/reagento/dishka). Nothing in the
application constructs its own collaborators: a class declares what it needs in
`__init__`, and the container supplies it.

## Scopes

Two, and only two:

- **`Scope.APP`** - created once, lives until shutdown. Anything holding a
  connection pool.
- **`Scope.REQUEST`** - created per request, torn down when it ends. Anything
  holding per-request state.

Getting this wrong is the usual DI bug. An `AsyncSession` at `Scope.APP` would
be shared by every concurrent request; an `AsyncEngine` at `Scope.REQUEST`
would build a new connection pool per request.

## What core provides

[`src/core/provider.py`](../src/core/provider.py):

| Type | Scope | Notes |
| --- | --- | --- |
| `Settings` | APP | the module singleton, not a fresh instance |
| `AsyncEngine` | APP | disposed on shutdown |
| `async_sessionmaker[AsyncSession]` | APP | `autoflush=False`, `expire_on_commit=False` |
| `AsyncSession` | REQUEST | closed when the request ends |
| `SessionManager` | REQUEST | what repositories take |
| `Redis` | APP | `aclose()` on shutdown |
| `RedisCache` | APP | key prefix from `settings.cache_key_prefix` |

The two pool owners are generator factories, so their cleanup is a `finally`:

```python
@provide(scope=Scope.APP)
async def get_async_engine(self, settings: Settings) -> AsyncIterable[AsyncEngine]:
    engine = make_async_engine(settings.db.url, ...)
    try:
        yield engine
    finally:
        await engine.dispose()
```

That `finally` runs when the container is closed, which the lifespan does on
shutdown. Without it every restart would leave pooled connections open on the
server until they timed out.

`get_settings` returns the module-level `settings` object rather than
constructing a new one - a second instance would re-parse `.env` and leave the
container holding a config that is not the one the rest of the code imported.

`FastapiProvider()` from dishka contributes the request-scoped `Request`
object, which is why a handler can ask for it alongside its use case.

## Writing a domain provider

One provider per domain, named `{Domain}Provider`:

```python
"""
Widget domain dishka provider.
"""

from dishka import Provider, Scope, provide

from .repositories import WidgetRepository
from .services import WidgetService
from .use_cases import ViewAllUseCase


class WidgetProvider(Provider):
    scope = Scope.REQUEST

    # === REPOSITORIES ===
    widget_repository = provide(WidgetRepository)

    # === SERVICES ===
    widget_service = provide(WidgetService)

    # === USE CASES ===
    view_all_use_case = provide(ViewAllUseCase)
```

- `scope = Scope.REQUEST` on the class applies to every `provide(...)` in the
  body. A domain rarely needs anything else; per-entry overrides use
  `provide(X, scope=Scope.APP)`.
- The bare `provide(Class)` form means dishka reads the class's `__init__`
  annotations and resolves them itself. `WidgetRepository(session_manager:
SessionManager)` gets its `SessionManager` from `CoreProvider` with no wiring
  written anywhere.
- The attribute name is the snake_case of the class. It is never referenced
  from outside; it just has to be unique in the body.
- The `# === ... ===` banners follow the layer order, innermost first, which
  makes a missing registration easy to spot.

Because every layer is constructor-injected, adding a dependency to a service
is a one-line change to its `__init__` - the provider does not change at all.

### Binding to a Protocol

To expose a service across a domain boundary, provide it _as_ the protocol:

```python
widget_service = provide(WidgetService, provides=WidgetLookupProtocol)
```

Consumers then depend on `WidgetLookupProtocol` and cannot reach anything else
in the domain. See
[`docs/domain.md`](domain.md#interfacespy).

## Registering the provider

[`src/di.py`](../src/di.py):

```python
def setup_async_container(*extra_providers: Provider) -> AsyncContainer:
    """
    Creates async dependencies application container.

    `extra_providers` for test dependencies substitution (provider with `override=True`
    substitutes original).
    """
    return make_async_container(
        # Core providers
        FastapiProvider(),
        CoreProvider(),
        # Apps providers
        WidgetProvider(),
        *extra_providers,
    )
```

Domain providers go under `# Apps providers`, and `*extra_providers` stays
last. dishka resolves the last registration of a type, so anything the caller
passes in wins - which is the whole mechanism behind test overrides. A provider
added after it would silently win instead.

Each call returns a **new** container. `create_app()` makes one and hands it to
`setup_dishka`, which puts it on `app.state.dishka_container`.

## Using it in a route

```python
from dishka.integrations.fastapi import FromDishka, inject


@router.get("", status_code=status.HTTP_200_OK)
@inject
async def view_all(
    use_case: FromDishka[ViewAllUseCase],
    pagination: Pagination,
) -> PaginationResultSchema[WidgetListReadSchema]:
    return await use_case.execute(pagination=pagination)
```

`@inject` goes below the route decorator, and only handlers that actually
resolve something need it. `FromDishka[...]` parameters come from the container;
everything else is ordinary FastAPI.

## Overriding a dependency in tests

The recipe from [`tests/unit/test_di.py`](../tests/unit/test_di.py):

```python
class CacheOverrideProvider(Provider):
    @provide(scope=Scope.APP, override=True)
    def get_redis_cache(self) -> RedisCache:
        return fake_cache


container = setup_async_container(CacheOverrideProvider())
try:
    assert await container.get(RedisCache) is fake_cache
finally:
    await container.close()
```

`override=True` is required - without it dishka rejects the duplicate
registration instead of replacing it. Always close the container in a
`finally`, or `Scope.APP` resources stay open for the rest of the session.

For an HTTP test, build the app and pass the container in the same way, or use
the `create_app()` + `httpx.ASGITransport` fixtures from
[`tests/unit/apps/test_healthz.py`](../tests/unit/apps/test_healthz.py) - those
never run the lifespan, so nothing connects.

## Using it outside a request

A CLI command, a worker or a script has no request to hang a scope off, so it
enters one itself:

```python
container = setup_async_container()
try:
    async with container() as request_container:
        service = await request_container.get(WidgetService)
        await service.do_work()
finally:
    await container.close()
```

Calling the container opens `Scope.REQUEST`; leaving the `async with` closes the
session. The outer `finally` is what releases the `Scope.APP` resources - the
engine and the Redis client - and skipping it leaves the process holding open
connections.

## Inspecting the graph

```sh
uv run --frozen python -m src.cli di graph
uv run --frozen python -m src.cli di graph -o /tmp/graph.html
```

Renders the resolution graph as a Mermaid diagram via `dishka.plotter`. The
default output is `docs/di_graph.html`, which is a build artefact and is
git-ignored. Useful for finding a dependency that resolves at the wrong scope.
