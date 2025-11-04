import pytest

from src.core.utils.case_converter import to_snake_case


@pytest.mark.parametrize(
    "input_string, output_string",
    (
        ("PascalCase", "pascal_case"),
        ("OneTwoThreeFourFiveSix", "one_two_three_four_five_six"),
        ("String", "string"),
        ("camelCaseString", "camel_case_string"),
        ("string", "string"),
    ),
)
def test_to_snake_case(input_string: str, output_string: str):
    assert to_snake_case(input_string) == output_string
