import pytest

from src.core.exceptions import (
    ModelIdRequiredError,
    ModelNotFoundError,
    SortingFieldNotFoundError,
)


class FakeModel:
    pass


class TestModelNotFoundError:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("FakeModel", "Unable to find FakeModel model"),
            (FakeModel, "Unable to find FakeModel model"),
        ],
        ids=("string_model", "cls_model"),
    )
    def test_msg_render_model_name(self, model, expected) -> None:
        assert ModelNotFoundError(model).msg == expected

    @pytest.mark.parametrize(
        ("model_id", "expected"),
        [
            (1, "Unable to find FakeModel model with id: 1"),
            ("abc", "Unable to find FakeModel model with id: abc"),
        ],
        ids=("int_id", "str_id"),
    )
    def test_msg_render_single_id(self, model_id, expected) -> None:
        assert ModelNotFoundError("FakeModel", model_id=model_id).msg == expected

    @pytest.mark.parametrize(
        ("model_id", "expected"),
        [
            ([], "Unable to find FakeModel model with ids: []"),
            ([1, 2, 3], "Unable to find FakeModel model with ids: [1, 2, 3]"),
            (("abc", "cba"), "Unable to find FakeModel model with ids: [abc, cba]"),
            ((1, "abc"), "Unable to find FakeModel model with ids: [1, abc]"),
        ],
        ids=("empty", "list", "tuple", "mixed"),
    )
    def test_msg_render_multiple_ids(self, model_id, expected) -> None:
        assert ModelNotFoundError("FakeModel", model_id=model_id).msg == expected

    @pytest.mark.parametrize(
        ("model_id", "message", "expected"),
        [
            (1, "Fake", "Unable to find FakeModel model with id: 1. Fake"),
            (None, "Fake", "Unable to find FakeModel model. Fake"),
            (1, "", "Unable to find FakeModel model with id: 1"),
        ],
        ids=("both", "only_message", "empty_str"),
    )
    def test_msg_render_with_model_id_and_message(
        self, model_id, message, expected
    ) -> None:
        exc = ModelNotFoundError("FakeModel", model_id=model_id, message=message)
        assert exc.msg == expected


class TestModelIdRequiredError:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("FakeModel", "Model FakeModel cannot be updated without an id."),
            (FakeModel, "Model FakeModel cannot be updated without an id."),
        ],
        ids=("string_model", "cls_model"),
    )
    def test_msg_render_model_name(self, model, expected) -> None:
        assert ModelIdRequiredError(model).msg == expected

    @pytest.mark.parametrize(
        ("schema", "expected"),
        [
            (
                "ABC",
                "Model Fake cannot be updated without an id. Set it on the ABC schema.",
            ),
            ("", "Model Fake cannot be updated without an id."),
        ],
        ids=("with_schema", "empty_string"),
    )
    def test_msg_render_schema(self, schema, expected) -> None:
        assert ModelIdRequiredError("Fake", schema=schema).msg == expected


class TestSortingFieldNotFoundError:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("ABC", "Sorting field not found 'ABC'."),
            ("", "Sorting field not found ''."),
        ],
        ids=("string", "empty_string"),
    )
    def test_msg_render_field(self, field, expected) -> None:
        expected_msg = f"{expected} No sorting fields are allowed."
        assert SortingFieldNotFoundError(field).msg == expected_msg

    @pytest.mark.parametrize(
        ("allowed", "expected"),
        [
            ("a", "Allowed fields: a."),
            (("a", "b"), "Allowed fields: a, b."),
            ("", "No sorting fields are allowed."),
            ([], "No sorting fields are allowed."),
            (None, "No sorting fields are allowed."),
        ],
        ids=("single", "multiple", "empty_str", "empty_list", "none"),
    )
    def test_msg_render_allowed_fields(self, allowed, expected) -> None:
        expected_msg = f"Sorting field not found 'ABC'. {expected}"
        assert (
            SortingFieldNotFoundError(
                "ABC",
                allowed_fields=allowed,
            ).msg
            == expected_msg
        )
