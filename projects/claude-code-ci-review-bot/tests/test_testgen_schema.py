"""Offline tests for the canonical test-gen schema (TR2). No CLI, no network."""

import json

import jsonschema
import pytest

import testgen_schema


def _valid_tests_obj() -> dict:
    return {
        "tests": [
            {
                "target": {"file": "src/discount.py", "symbol": "apply_discount"},
                "test_name": "test_apply_discount_rejects_out_of_range",
                "case": "rate-out-of-range",
                "description": "A rate above 1 raises ValueError",
                "test_code": (
                    "import pytest\nfrom discount import apply_discount\n\n"
                    "def test_apply_discount_rejects_out_of_range():\n"
                    "    with pytest.raises(ValueError):\n"
                    "        apply_discount(100, 2)"
                ),
            }
        ]
    }


def test_schema_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(testgen_schema.TESTGEN_SCHEMA)


def test_valid_tests_object_passes():
    testgen_schema.validate_tests_obj(_valid_tests_obj())


def test_empty_tests_is_valid():
    # If every behavior is already covered, an empty tests array is legitimate.
    testgen_schema.validate_tests_obj({"tests": []})


def test_missing_case_raises():
    obj = _valid_tests_obj()
    del obj["tests"][0]["case"]
    with pytest.raises(jsonschema.ValidationError):
        testgen_schema.validate_tests_obj(obj)


def test_missing_target_raises():
    obj = _valid_tests_obj()
    del obj["tests"][0]["target"]
    with pytest.raises(jsonschema.ValidationError):
        testgen_schema.validate_tests_obj(obj)


def test_target_wrong_type_raises():
    obj = _valid_tests_obj()
    obj["tests"][0]["target"] = "src/discount.py"  # should be an object
    with pytest.raises(jsonschema.ValidationError):
        testgen_schema.validate_tests_obj(obj)


def test_extra_top_level_key_rejected():
    obj = _valid_tests_obj()
    obj["findings"] = []  # additionalProperties: False at the top level
    with pytest.raises(jsonschema.ValidationError):
        testgen_schema.validate_tests_obj(obj)


def test_as_json_string_round_trips():
    parsed = json.loads(testgen_schema.as_json_string())
    assert parsed == testgen_schema.TESTGEN_SCHEMA
    assert parsed["type"] == "object"
    assert parsed["required"] == ["tests"]
