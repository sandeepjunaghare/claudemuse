"""Canonical test-suggestion JSON Schema — the test-gen machine contract (TR2).

A *second* canonical schema, sibling to ``schema.FINDINGS_SCHEMA`` and entirely
distinct from it: test generation is a separate output path with a ``tests``
array, not a ``findings`` array. Like the findings schema, this single ``dict``
is the one source of truth — it is serialized and passed to
``claude -p --json-schema`` (constraining the model's structured output) *and*
used post-hoc to validate whatever comes back, so the CLI contract and the
parser cannot drift apart.

``--json-schema`` maps the top-level object to a tool input schema, so the top
level MUST be an object with a named array property; a bare-array top level is
rejected by the CLI.
"""

import json

import jsonschema

#: The test-suggestion shape emitted per proposed test. Mirrors the discipline of
#: ``schema.FINDINGS_SCHEMA`` (top-level object, one named array,
#: ``additionalProperties: False``). ``case`` is a controlled kebab-case slug —
#: the identity used for within-run dedupe (the test-gen analog of a finding's
#: ``detected_pattern``), so it is required.
TESTGEN_SCHEMA = {
    "type": "object",
    "required": ["tests"],
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "target",
                    "test_name",
                    "case",
                    "description",
                    "test_code",
                ],
                "properties": {
                    "target": {
                        "type": "object",
                        "required": ["file", "symbol"],
                        "properties": {
                            "file": {"type": "string"},
                            "symbol": {"type": "string"},
                        },
                    },
                    "test_name": {"type": "string"},
                    "case": {"type": "string"},
                    "description": {"type": "string"},
                    "test_code": {"type": "string"},
                },
            },
        }
    },
    "additionalProperties": False,
}


def as_json_string() -> str:
    """Serialize the schema for the ``--json-schema`` CLI flag."""
    return json.dumps(TESTGEN_SCHEMA)


def validate_tests_obj(obj: object) -> None:
    """Validate a parsed test-suggestions object against the canonical schema.

    Raises ``jsonschema.ValidationError`` if ``obj`` does not conform. Even
    though the CLI already constrains output, we re-validate here so a schema
    violation is surfaced (never silently emitted) — TR2.
    """
    jsonschema.validate(instance=obj, schema=TESTGEN_SCHEMA)
