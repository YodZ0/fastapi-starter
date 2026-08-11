import asyncio
from functools import wraps


def typer_async(func):
    """
    Async Typer decorator.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))

    return wrapper
