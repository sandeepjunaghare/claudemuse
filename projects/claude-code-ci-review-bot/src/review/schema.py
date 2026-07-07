"""Canonical findings JSON Schema — the machine-readable contract (TR2).

This single ``dict`` is the one source of truth: it is serialized and passed to
``claude -p --json-schema`` (constraining the model's structured output) *and*
used post-hoc to validate whatever comes back. Because the schema drives both
sides, there is no way for the CLI contract and the parser to drift apart.

The full canonical shape (including ``detected_pattern`` and ``category``) is
present from day one even though Phase 1's minimal prompt won't populate those
fields meaningfully — this avoids reshaping the contract in later phases.
"""

import json

import jsonschema

#: The finding shape emitted per issue (PRD §10). ``--json-schema`` maps the
#: top-level object to a tool input schema, so the top level MUST be an object;
#: a bare-array top level is rejected by the CLI.
FINDINGS_SCHEMA = {
    "type": "object",
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "location",
                    "issue",
                    "severity",
                    "suggested_fix",
                    "detected_pattern",
                    "category",
                ],
                "properties": {
                    "location": {
                        "type": "object",
                        "required": ["file", "line"],
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                        },
                    },
                    "issue": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                    "suggested_fix": {"type": "string"},
                    "detected_pattern": {"type": "string"},
                    "category": {"type": "string"},
                },
            },
        }
    },
    "additionalProperties": False,
}


def as_json_string() -> str:
    """Serialize the schema for the ``--json-schema`` CLI flag."""
    return json.dumps(FINDINGS_SCHEMA)


def validate_findings_obj(obj: object) -> None:
    """Validate a parsed findings object against the canonical schema.

    Raises ``jsonschema.ValidationError`` if ``obj`` does not conform. Even
    though the CLI already constrains output, we re-validate here so a schema
    violation is surfaced (never silently posted) — TR2.
    """
    jsonschema.validate(instance=obj, schema=FINDINGS_SCHEMA)
