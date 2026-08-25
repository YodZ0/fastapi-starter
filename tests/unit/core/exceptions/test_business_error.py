import pytest

from src.core.enums import ModelActionEnum
from src.core.exceptions import (
    BusinessLogicException,
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
    SearchFieldNotFoundError,
    SortingFieldNotFoundError,
)

TRACEBACK_HEADER = "Traceback (most recent call last):"


def raised(error: BusinessLogicException) -> BusinessLogicException:
    """
    Return `error` after it has actually travelled through a `raise`.
    """
    try:
        raise error
    except BusinessLogicException as caught:
        return caught


class TestBusinessLogicError:
    @pytest.mark.parametrize(
        ("error", "error_type"),
        [
            (ModelIdRequiredError("A"), "model_id_required"),
            (ModelIntegrityError("A", ModelActionEnum.INSERT), "model_integrity"),
            (ModelNotFoundError("A"), "model_not_found"),
            (SearchFieldNotFoundError("A"), "search_field_not_found"),
            (SortingFieldNotFoundError("A"), "sorting_field_not_found"),
        ],
        ids=(
            "model_id_required",
            "model_integrity",
            "model_not_found",
            "search_field_not_found",
            "sorting_field_not_found",
        ),
    )
    def test_render_error_type(self, error, error_type) -> None:
        """
        `type` is a public API contract.
        """
        assert error.type == error_type

    def test_str_renders_msg(self) -> None:
        error = ModelNotFoundError("FakeModel", model_id=1)

        assert error.args == ()
        assert str(error) == error.msg

    def test_schema_carries_type_and_msg(self) -> None:
        error = ModelNotFoundError("FakeModel", model_id=1)
        schema = error.get_schema(debug=False)

        assert schema.type == "model_not_found"
        assert schema.msg == "Unable to find FakeModel model with id: 1"

    def test_schema_hides_traceback_without_debug(self) -> None:
        error = raised(ModelNotFoundError("FakeModel", model_id=1))
        assert error.get_schema(debug=False).traceback is None

    def test_schema_renders_traceback_with_debug(self) -> None:
        error = raised(ModelNotFoundError("FakeModel", model_id=1))
        rendered = error.get_schema(debug=True).traceback

        assert rendered is not None
        assert rendered.startswith(TRACEBACK_HEADER)
        assert rendered.rstrip().endswith(f"ModelNotFoundError: {error.msg}")

    def test_schema_renders_traceback_of_unraised_error(self) -> None:
        error = ModelNotFoundError("FakeModel", model_id=1)
        rendered = error.get_schema(debug=True).traceback

        assert rendered is not None
        assert TRACEBACK_HEADER not in rendered
        assert rendered.rstrip().endswith(f"ModelNotFoundError: {error.msg}")
