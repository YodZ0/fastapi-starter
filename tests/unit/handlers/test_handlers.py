from fastapi import FastAPI

from src.core.exceptions import BusinessLogicException
from src.handlers import apply_exception_handlers


class TestApplyExceptionHandlers:
    def test_every_business_exception_is_registered(self) -> None:
        """
        Every business exception must have its own handler.

        The expected set is read from `BusinessLogicException.__subclasses__()`
        rather than listed here: an exception added without a handler falls
        through to `internal_server_error_handler`, turning a 400-class input
        error into a 500 plus an "Unexpected error occurred!" traceback in the
        log. Only direct subclasses are required - Starlette resolves a handler
        by walking the MRO, so a subclass of an already handled error is covered
        by its parent. Classes defined outside `src` are filtered out: test
        doubles subclass the base as well, and they never reach a running app.
        """
        app = FastAPI()

        apply_exception_handlers(app)

        expected = {
            exception
            for exception in BusinessLogicException.__subclasses__()
            if exception.__module__.startswith("src.")
        }
        missing = expected - set(app.exception_handlers)
        assert not missing, (
            "no exception handler registered for: "
            f"{sorted(exc.__name__ for exc in missing)}"
        )

    def test_unexpected_error_is_registered(self) -> None:
        app = FastAPI()

        apply_exception_handlers(app)

        assert Exception in app.exception_handlers
