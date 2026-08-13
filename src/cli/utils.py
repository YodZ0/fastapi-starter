import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any


def typer_async[**P, R](
    func: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, R]:
    """
    Async Typer decorator.

    @wraps keeps __wrapped__ pointing at the coroutine function, which is what
    lets Typer read the original signature to build the command.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(func(*args, **kwargs))

    return wrapper
