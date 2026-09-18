# CLI

[Typer](https://typer.tiangolo.com/), invoked as a module:

```sh
uv run --frozen python -m src.cli --help
uv run --frozen python -m src.cli sys check
uv run --frozen python -m src.cli di graph -o docs/di_graph.html
```

There is no `fastapi-starter` console script on purpose: `pyproject.toml` sets
`[tool.uv] package = false`, so the project is a path package rather than an
installed distribution and a `[project.scripts]` entry would never be created.
`python -m src.cli` works from the repo root with no install step.

## Current commands

| Command | Does |
| --- | --- |
| `sys check` | prints `CLI is working!` - a smoke test for the entrypoint |
| `di graph [-o PATH]` | renders the dishka resolution graph to HTML |

## Structure

```text
src/cli/
├── __init__.py
├── __main__.py          # root Typer app; the only registration point
├── utils.py             # typer_async decorator
└── commands/
    ├── __init__.py      # empty - there is no autodiscovery
    ├── di.py            # di_app
    └── system.py        # system_app
```

Each module in `commands/` owns one `typer.Typer()` sub-app, and
[`src/cli/__main__.py`](../src/cli/__main__.py) mounts them:

```python
import typer

from .commands.di import di_app
from .commands.system import system_app

cli_app = typer.Typer()
cli_app.add_typer(system_app, name="sys", help="System commands")
cli_app.add_typer(di_app, name="di", help="DI (dishka) commands")


if __name__ == "__main__":
    cli_app()
```

## Adding a command to an existing group

Open the module and add a decorated function:

```python
from src.settings import settings


@system_app.command(name="version", help="Print the application title.")
def print_version() -> None:
    typer.echo(settings.app.title)
```

It is reachable immediately as `python -m src.cli sys version`.

Four constraints will otherwise fail the quality gate:

- **Annotate everything.** mypy runs with `strict = true` over `src`, so a
  missing return type is an error, not a warning.
- **`typer.echo`, not `print`.** ruff `T20` bans `print` in `src/`.
- **Options and arguments use `Annotated`:**
  ```python
  output: Annotated[Path, typer.Option("--output", "-o", help="Output dir.")] = DEFAULT
  ```
- **Fail with `raise typer.Exit(1) from e`,** so the shell gets a non-zero
  status.

## Adding a new group

1. Create `src/cli/commands/{group}.py`:

   ```python
   import typer

   widgets_app = typer.Typer()


   @widgets_app.command(name="count", help="Count widgets.")
   def count_widgets() -> None:
       typer.echo("0")
   ```

2. Register it in `src/cli/__main__.py` - an import plus one line:

   ```python
   from .commands.widgets import widgets_app

   cli_app.add_typer(widgets_app, name="widgets", help="Widget commands")
   ```

That is the **only** registration point. `src/cli/commands/__init__.py` is
empty and there is no discovery loop to extend, so a module that is never
imported there is simply not part of the CLI.

Sub-apps are imported relatively (`from .commands.x import ...`) in
`__main__.py`; command modules import application code absolutely
(`from src.di import ...`).

## Async commands

Typer commands are synchronous. `typer_async` from
[`src/cli/utils.py`](../src/cli/utils.py) bridges the gap:

```python
from src.cli.utils import typer_async


@widgets_app.command(name="sync", help="Sync widgets from upstream.")
@typer_async
async def sync_widgets() -> None:
    ...
```

Decorator order matters - `@typer_async` goes **below** the `command`
decorator, so Typer registers the wrapper. `@wraps` keeps `__wrapped__`
pointing at the coroutine function, which is what lets Typer read the original
signature to build the command options.

The wrapper is `asyncio.run(func(...))`, so each invocation gets its own event
loop.

## Commands that need application dependencies

Build a container, enter request scope, and close it in a `finally`:

```python
@widgets_app.command(name="count", help="Count widgets.")
@typer_async
async def count_widgets() -> None:
    container = setup_async_container()
    try:
        async with container() as request_container:
            service = await request_container.get(WidgetService)
            result = await service.count()
    finally:
        await container.close()

    typer.echo(result)
```

The `finally` is not optional: `Scope.APP` resources - the database engine and
the Redis client - are released only by `await container.close()`, and a
command that skips it exits holding open connections. Details in
[`docs/di.md`](di.md#using-it-outside-a-request).

Note that `di graph` does *not* do this. It only inspects the graph and never
enters a scope, so nothing is opened for it to release.

## Coverage

`src/cli/` is deliberately outside the covered set - see the comment above
`[tool.coverage.run]` in `pyproject.toml`. Process entrypoints are exercised by
running them, not by unit tests. A command with real logic in it is worth
testing; keep that logic in a service and the command thin, and it is covered
where it lives.
