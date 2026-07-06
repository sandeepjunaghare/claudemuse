"""Phase 1: schemas generate valid tool JSON Schema; nullable + extensible-enum hold (TR1/TR2)."""

import extract
from schemas import SCHEMA_REGISTRY, Contract, DocumentMetadata, Invoice


def _collect_enum_values(node):
    """Recursively gather every `enum` value anywhere in a JSON Schema."""
    found = []
    if isinstance(node, dict):
        if "enum" in node and isinstance(node["enum"], list):
            found += node["enum"]
        for v in node.values():
            found += _collect_enum_values(v)
    elif isinstance(node, list):
        for v in node:
            found += _collect_enum_values(v)
    return found


def test_every_schema_builds_a_tool():
    for doc_type in SCHEMA_REGISTRY:
        tool = extract.build_tool(doc_type)
        assert tool["name"] == f"extract_{doc_type}"
        assert tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_tool_input_schema_is_generated_from_pydantic():
    # Single source of truth — never hand-written.
    assert extract.build_tool("invoice")["input_schema"] == Invoice.model_json_schema()


def test_maybe_absent_fields_are_not_required():
    # FR2: nothing is required, so the model never fabricates to satisfy the schema.
    schema = Invoice.model_json_schema()
    assert "po_number" in schema["properties"]
    assert "po_number" not in schema.get("required", [])


def test_extensible_enum_has_other_and_unclear():
    for model_cls in (Contract, DocumentMetadata):
        values = _collect_enum_values(model_cls.model_json_schema())
        assert "other" in values, model_cls
        assert "unclear" in values, model_cls


def test_output_always_validates_even_when_empty():
    # An all-absent document still produces a valid instance (nulls / empty lists).
    assert Invoice.model_validate({}).po_number is None
    assert Invoice.model_validate({}).line_items == []
    assert Contract.model_validate({}).category == "unclear"
