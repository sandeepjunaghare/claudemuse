"""Offline tests for finding emission (FR1). Structural assertions only."""

from parse import Finding, Location
from post import emit, format_comment


def _finding() -> Finding:
    return Finding(
        location=Location("src/mod.py", 7),
        issue="boom",
        severity="high",
        suggested_fix="fix it",
        detected_pattern="null-deref",
        category="correctness",
    )


def test_format_comment_contains_file_line_severity_and_fix():
    text = format_comment(_finding())
    assert "src/mod.py:7" in text  # file:line mapping (the acceptance gate)
    assert "[high]" in text
    assert "fix it" in text
    assert "null-deref" in text


def test_emit_prints_count_header_and_one_line_per_finding(capsys):
    emit([_finding(), _finding()])
    out = capsys.readouterr().out
    assert "2 finding(s)" in out
    assert out.count("src/mod.py:7") == 2


def test_emit_zero_findings(capsys):
    emit([])
    out = capsys.readouterr().out
    assert "0 finding(s)" in out
