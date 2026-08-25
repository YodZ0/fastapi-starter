import uuid

import pytest

from src.core.enums import ModelActionEnum
from src.core.exceptions import (
    ModelIdRequiredError,
    ModelIntegrityError,
    ModelNotFoundError,
    SearchFieldNotFoundError,
    SortingFieldNotFoundError,
)


class FakeModel:
    pass


UUID_A = uuid.UUID("00000000-0000-0000-0000-000000000001")
UUID_B = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

EXPECTED_ACTION_PHRASES = {
    ModelActionEnum.INSERT: "insert",
    ModelActionEnum.UPDATE: "update",
    ModelActionEnum.UPSERT: "insert or update",
    ModelActionEnum.DELETE: "delete",
    ModelActionEnum.BULK_INSERT: "bulk insert",
    ModelActionEnum.BULK_UPDATE: "bulk update",
    ModelActionEnum.BULK_DELETE: "bulk delete",
}


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
            (("cba", "abc"), "Unable to find FakeModel model with ids: [abc, cba]"),
            ([10, 2], "Unable to find FakeModel model with ids: [2, 10]"),
            (
                {"d", "b", "a", "c"},
                "Unable to find FakeModel model with ids: [a, b, c, d]",
            ),
            (
                {UUID_B, UUID_A},
                f"Unable to find FakeModel model with ids: [{UUID_A}, {UUID_B}]",
            ),
        ],
        ids=("empty", "tuple", "int_sorts_as_number", "str_set", "uuid_set"),
    )
    def test_msg_render_multiple_ids(self, model_id, expected) -> None:
        assert ModelNotFoundError("FakeModel", model_id=model_id).msg == expected

    def test_msg_render_multiple_ids_is_order_independent(self) -> None:
        ids = ["b", "a", "c"]
        exc_a = ModelNotFoundError("FakeModel", model_id=ids)
        exc_b = ModelNotFoundError("FakeModel", model_id=list(reversed(ids)))
        assert exc_a.msg == exc_b.msg

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


class TestSearchFieldNotFoundError:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("ABC", "Search field not found 'ABC'."),
            ("", "Search field not found ''."),
        ],
        ids=("string", "empty_string"),
    )
    def test_msg_render_field(self, field, expected) -> None:
        expected_msg = f"{expected} No searching fields are allowed."
        assert SearchFieldNotFoundError(field).msg == expected_msg

    @pytest.mark.parametrize(
        ("allowed", "expected"),
        [
            ("a", "Allowed fields: a."),
            (("a", "b"), "Allowed fields: a, b."),
            ("", "No searching fields are allowed."),
            ([], "No searching fields are allowed."),
            (None, "No searching fields are allowed."),
        ],
        ids=("single", "multiple", "empty_str", "empty_list", "none"),
    )
    def test_msg_render_allowed_fields(self, allowed, expected) -> None:
        expected_msg = f"Search field not found 'ABC'. {expected}"
        assert (
            SearchFieldNotFoundError(
                "ABC",
                allowed_fields=allowed,
            ).msg
            == expected_msg
        )


class TestModelIntegrityError:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("FakeModel", "Integrity error for model FakeModel insert."),
            (FakeModel, "Integrity error for model FakeModel insert."),
        ],
        ids=("string_model", "cls_model"),
    )
    def test_msg_render_model_name(self, model, expected) -> None:
        exc = ModelIntegrityError(model, ModelActionEnum.INSERT)
        assert exc.msg == expected

    def test_every_action_has_an_expected_phrase(self) -> None:
        """
        Guard EXPECTED_ACTION_PHRASES against the enum growing underneath it.
        """
        assert set(EXPECTED_ACTION_PHRASES) == set(ModelActionEnum)

    @pytest.mark.parametrize("model_action", list(ModelActionEnum))
    def test_msg_render_model_action(self, model_action) -> None:
        expected = EXPECTED_ACTION_PHRASES[model_action]
        expected_msg = f"Integrity error for model FakeModel {expected}."
        assert ModelIntegrityError("FakeModel", action=model_action).msg == expected_msg

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("ABC", "Integrity error for model FakeModel insert. ABC."),
            ("", "Integrity error for model FakeModel insert."),
        ],
        ids=("string", "empty"),
    )
    def test_msg_render_message(self, message, expected) -> None:
        exc = ModelIntegrityError("FakeModel", ModelActionEnum.INSERT, message=message)
        assert exc.msg == expected
