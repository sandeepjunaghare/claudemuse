"""Offline tests for the event-stream parser (TR2). No CLI, no network."""

import json

import pytest

import parse


def test_golden_output_parses_to_one_finding(sample_output):
    review = parse.parse_result(sample_output)
    assert review.is_error is False
    assert len(review.findings) == 1
    f = review.findings[0]
    assert f.location.file == "src/auth.py"
    assert f.location.line == 42
    assert f.severity == "high"


def test_error_envelope_surfaces_terminal_reason():
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "result",
            "subtype": "error_during_execution",
            "is_error": True,
            "terminal_reason": "error",
        },
    ]
    review = parse.parse_result(json.dumps(events))
    assert review.is_error is True
    assert review.findings == []
    assert review.terminal_reason == "error"


def test_structured_output_absent_falls_back_to_result_string():
    payload = {
        "findings": [
            {
                "location": {"file": "a.py", "line": 3},
                "issue": "x",
                "severity": "low",
                "suggested_fix": "y",
                "detected_pattern": "p",
                "category": "correctness",
            }
        ]
    }
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "terminal_reason": "completed",
            "result": json.dumps(payload),
            # note: no "structured_output" key
        },
    ]
    review = parse.parse_result(json.dumps(events))
    assert review.is_error is False
    assert len(review.findings) == 1
    assert review.findings[0].location.file == "a.py"


def test_non_json_stdout_raises_parse_error():
    with pytest.raises(parse.ParseError):
        parse.parse_result("not json at all")


def test_no_result_element_raises_parse_error():
    events = [{"type": "system", "subtype": "init"}]
    with pytest.raises(parse.ParseError):
        parse.parse_result(json.dumps(events))


def test_empty_array_raises_parse_error():
    with pytest.raises(parse.ParseError):
        parse.parse_result("[]")
