"""Phase 1: the router picks `any` vs forced `tool_choice` correctly (TR1). Pure — no API."""

import pytest

import extract


def test_tool_name_roundtrip():
    assert extract.tool_name_for("invoice") == "extract_invoice"
    assert extract.doc_type_from_tool_name("extract_invoice") == "invoice"


def test_unknown_type_routes_to_any_over_content_schemas():
    tools, tool_choice = extract.route(None)
    assert tool_choice == {"type": "any"}
    names = {t["name"] for t in tools}
    # Competing content schemas only — metadata is a separate forced step.
    assert names == {"extract_invoice", "extract_contract", "extract_paper"}


def test_known_type_forces_that_tool():
    tools, tool_choice = extract.route("invoice")
    assert tool_choice == {"type": "tool", "name": "extract_invoice"}
    # Full registry is passed so few-shot tool names still resolve.
    assert "extract_metadata" in {t["name"] for t in tools}


def test_metadata_is_a_forced_first_step():
    _tools, tool_choice = extract.route("metadata")
    assert tool_choice == {"type": "tool", "name": "extract_metadata"}


def test_unknown_doc_type_raises():
    with pytest.raises(KeyError):
        extract.route("bogus")
