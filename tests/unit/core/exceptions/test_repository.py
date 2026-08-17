import pytest

from src.core.exceptions import (
    ModelIdRequiredError,
    ModelNotFoundError,
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
