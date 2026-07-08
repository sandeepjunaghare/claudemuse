"""Parse the Claude Code event stream into validated ``Finding`` objects (TR2).

``claude -p --output-format json`` prints a JSON *array* of event objects
(system init, assistant, tool_result, and a final ``result``). We locate the
``type == "result"`` element and read its structured payload — preferring the
already-parsed ``structured_output`` dict, falling back to ``json.loads`` on the
``result`` string. The payload is then re-validated against the canonical schema
(belt-and-suspenders per TR2) before being materialized into dataclasses.

This module is subprocess-free so it unit-tests offline against a recorded
golden fixture — no CLI, no network, no credentials.
"""

import json
from dataclasses import dataclass

import schema


class ParseError(Exception):
    """Raised when the CLI stdout cannot be parsed into a review result."""


@dataclass
class Location:
    """A file:line pointer for an inline comment."""

    file: str
    line: int


@dataclass
class Finding:
    """One review finding — the machine-parseable unit that maps to a comment."""

    location: Location
    issue: str
    severity: str
    suggested_fix: str
    detected_pattern: str
    category: str


@dataclass
class ParsedReview:
    """Outcome of parsing one ``claude -p`` run."""

    findings: list
    is_error: bool
    terminal_reason: "str | None"
    raw: list


def parse_result(stdout: str) -> ParsedReview:
    """Parse CLI stdout into a ``ParsedReview``.

    Args:
        stdout: The raw stdout from ``claude -p --output-format json`` — a JSON
            array of event objects. (stdout only; the stderr connectors warning
            must never be merged in.)

    Returns:
        A ``ParsedReview``. On a CLI ``is_error`` envelope, returns an empty
        findings list with ``is_error=True`` and the terminal reason surfaced.

    Raises:
        ParseError: if stdout is not JSON, not a non-empty list, or contains no
            ``result`` element. The offending ``stdout`` is preserved in the
            message for debugging.
    """
    try:
        events = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ParseError(f"stdout is not valid JSON: {exc}\n---\n{stdout!r}") from exc

    if not isinstance(events, list) or not events:
        raise ParseError(f"expected a non-empty JSON array, got: {stdout!r}")

    result_elem = next((e for e in events if e.get("type") == "result"), None)
    if result_elem is None:
        raise ParseError(f"no element with type=='result' in event stream: {stdout!r}")

    terminal_reason = result_elem.get("terminal_reason")

    if result_elem.get("is_error"):
        return ParsedReview(
            findings=[],
            is_error=True,
            terminal_reason=terminal_reason,
            raw=events,
        )

    payload = result_elem.get("structured_output")
    if payload is None:
        # Fallback: the same data is available as a JSON string under "result".
        raw_result = result_elem.get("result")
        try:
            payload = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ParseError(
                f"result element has neither structured_output nor parseable "
                f"result string: {result_elem!r}"
            ) from exc

    # Belt-and-suspenders: validate even though --json-schema constrained output.
    schema.validate_findings_obj(payload)

    findings = [
        Finding(
            location=Location(
                file=f["location"]["file"],
                line=f["location"]["line"],
            ),
            issue=f["issue"],
            severity=f["severity"],
            suggested_fix=f["suggested_fix"],
            detected_pattern=f["detected_pattern"],
            category=f["category"],
        )
        for f in payload["findings"]
    ]

    return ParsedReview(
        findings=findings,
        is_error=False,
        terminal_reason=terminal_reason,
        raw=events,
    )
