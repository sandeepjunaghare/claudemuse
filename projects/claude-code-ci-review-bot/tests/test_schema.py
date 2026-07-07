"""Offline tests for the canonical findings schema (TR2)."""

import json

import jsonschema
import pytest

import schema


def _valid_findings_obj() -> dict:
    return {
        "findings": [
            {
                "location": {"file": "src/auth.py", "line": 42},
                "issue": "Token compared with == allows timing attack",
                "severity": "high",
                "suggested_fix": "Use hmac.compare_digest",
                "detected_pattern": "timing-unsafe-comparison",
                "category": "security",
            }
        ]
    }


def test_schema_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(schema.FINDINGS_SCHEMA)


def test_valid_findings_object_passes():
    schema.validate_findings_obj(_valid_findings_obj())


def test_empty_findings_is_valid():
    schema.validate_findings_obj({"findings": []})


def test_missing_severity_raises():
    obj = _valid_findings_obj()
    del obj["findings"][0]["severity"]
    with pytest.raises(jsonschema.ValidationError):
        schema.validate_findings_obj(obj)


def test_severity_not_in_enum_raises():
    obj = _valid_findings_obj()
    obj["findings"][0]["severity"] = "blocker"
    with pytest.raises(jsonschema.ValidationError):
        schema.validate_findings_obj(obj)


def test_as_json_string_round_trips():
    assert json.loads(schema.as_json_string()) == schema.FINDINGS_SCHEMA
