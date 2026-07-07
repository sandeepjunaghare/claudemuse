"""Offline unit tests for severity normalization + canonical override (TR5).

Pure functions only — no CLI, no network. Asserts on structure/constants, never
on model wording (PRD principle 5).
"""

import pytest

import severity
from parse import Finding, Location


def _finding(sev="medium", pattern="", file="a.py", line=1):
    return Finding(
        location=Location(file, line),
        issue="x",
        severity=sev,
        suggested_fix="fix",
        detected_pattern=pattern,
        category="correctness",
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("BLOCKER", "critical"),
        ("blocker", "critical"),
        ("error", "high"),
        ("warn", "medium"),
        ("warning", "medium"),
        ("nit", "low"),
        ("minor", "low"),
        ("critical", "critical"),
        ("HIGH", "high"),
        ("  low  ", "low"),
        ("nonsense", "medium"),  # unknown → safe default
        ("", "medium"),
    ],
)
def test_normalize_severity(raw, expected):
    assert severity.normalize_severity(raw) == expected


def test_canonical_severity_overrides_known_pattern():
    # Model mislabels a none-deref as "low"; the pattern override forces "high".
    f = _finding(sev="low", pattern="none-deref")
    assert severity.canonical_severity(f) == "high"


def test_canonical_severity_unknown_pattern_falls_back_to_model_label():
    f = _finding(sev="warn", pattern="some-novel-slug")
    # No override → normalize the model's own label.
    assert severity.canonical_severity(f) == "medium"


def test_cross_file_pattern_is_critical():
    f = _finding(sev="low", pattern="cross-file-key-mismatch")
    assert severity.canonical_severity(f) == "critical"


def test_apply_canonical_severity_no_mutation_and_idempotent():
    original = _finding(sev="low", pattern="none-deref")
    once = severity.apply_canonical_severity([original])
    # Input not mutated.
    assert original.severity == "low"
    # New object with canonical severity.
    assert once[0].severity == "high"
    assert once[0] is not original
    # Idempotent.
    twice = severity.apply_canonical_severity(once)
    assert twice[0].severity == "high"


def test_sort_by_severity_orders_critical_first():
    findings = [
        _finding(sev="low", pattern="", file="a.py", line=1),
        _finding(sev="critical", pattern="", file="b.py", line=2),
        _finding(sev="medium", pattern="", file="c.py", line=3),
        _finding(sev="high", pattern="", file="d.py", line=4),
    ]
    ordered = [f.severity for f in severity.sort_by_severity(findings)]
    assert ordered == ["critical", "high", "medium", "low"]


def test_severity_rank_monotonic():
    ranks = [severity.severity_rank(s) for s in severity.SEVERITY_LEVELS]
    assert ranks == sorted(ranks)
    assert ranks[0] < ranks[-1]  # critical more severe (lower rank) than low
