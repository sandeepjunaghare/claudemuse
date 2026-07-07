"""Offline unit tests for the pure precision/recall scorer (TR4/TR5).

No ``claude`` calls — imports only the pure scorer functions. This is the
ground-truth check that the metric itself is correct before any live number is
trusted.
"""

import metrics
from parse import Finding, Location

TOL = 3

CASES = [
    {
        "id": "none-deref",
        "file": "src/orders.py",
        "line": 24,
        "should_flag": True,
        "requires_integration_pass": False,
    },
    {
        "id": "settings-broad-except",
        "file": "src/settings.py",
        "line": 10,
        "should_flag": False,
        "requires_integration_pass": False,
    },
    {
        "id": "cross-file-key-mismatch",
        "file": "src/summary.py",
        "line": 14,
        "should_flag": True,
        "requires_integration_pass": True,
    },
]


def _f(file, line, pattern="none-deref"):
    return Finding(
        location=Location(file, line),
        issue="x",
        severity="high",
        suggested_fix="fix",
        detected_pattern=pattern,
        category="correctness",
    )


def test_perfect_single_pass_review():
    # Flags the eligible positive (none-deref), nothing else.
    findings = [_f("src/orders.py", 24)]
    r = metrics.score(findings, CASES, tolerance=TOL)
    assert (r.tp, r.fp, r.fn) == (1, 0, 0)
    assert r.precision == 1.0 and r.recall == 1.0 and r.f1 == 1.0
    assert r.matched == ["none-deref"]
    assert "cross-file-key-mismatch" in r.known_gaps


def test_flagging_should_not_case_is_false_positive():
    findings = [_f("src/orders.py", 24), _f("src/settings.py", 10, "broad-except")]
    r = metrics.score(findings, CASES, tolerance=TOL)
    assert r.tp == 1 and r.fp == 1
    assert r.precision == 0.5
    assert r.recall == 1.0


def test_missing_positive_is_false_negative():
    findings = []  # missed the none-deref
    r = metrics.score(findings, CASES, tolerance=TOL)
    assert r.tp == 0 and r.fn == 1
    assert r.recall == 0.0
    assert "none-deref" in r.missed
    # No findings, no FPs → precision defined as 1.0 (no false claims).
    assert r.precision == 1.0


def test_spurious_finding_on_unlabeled_line_is_fp():
    findings = [_f("src/orders.py", 24), _f("src/orders.py", 99, "made-up")]
    r = metrics.score(findings, CASES, tolerance=TOL)
    assert r.tp == 1 and r.fp == 1


def test_integration_case_excluded_from_single_pass_recall():
    # Only flag none-deref; the cross-file case must NOT count as an FN.
    findings = [_f("src/orders.py", 24)]
    r = metrics.score(findings, CASES, tolerance=TOL, single_pass=True)
    assert r.fn == 0
    assert r.known_gaps == ["cross-file-key-mismatch"]
    # With single_pass=False the cross-file case becomes an eligible positive.
    r2 = metrics.score(findings, CASES, tolerance=TOL, single_pass=False)
    assert r2.fn == 1
    assert r2.known_gaps == []


def test_known_gap_match_is_bonus_not_fp():
    # Catching the cross-file (integration-only) case in single-pass mode must
    # NOT be penalized as a false positive — precision stays clean.
    findings = [_f("src/orders.py", 24), _f("src/summary.py", 14, "cross-file-key-mismatch")]
    r = metrics.score(findings, CASES, tolerance=TOL, single_pass=True)
    assert r.tp == 1 and r.fp == 0
    assert r.precision == 1.0
    assert r.known_gap_hits == ["cross-file-key-mismatch"]
    # In multi-pass mode the same case is a real positive → a TP, not a gap hit.
    r2 = metrics.score(findings, CASES, tolerance=TOL, single_pass=False)
    assert r2.tp == 2 and r2.known_gap_hits == []


def test_line_tolerance_matching():
    # Finding at 26 matches a case at 24 within tolerance 3.
    findings = [_f("src/orders.py", 26)]
    r = metrics.score(findings, CASES, tolerance=TOL)
    assert r.tp == 1
    # Off by more than tolerance → miss (counts as FP + FN).
    findings_far = [_f("src/orders.py", 40)]
    r2 = metrics.score(findings_far, CASES, tolerance=TOL)
    assert r2.tp == 0 and r2.fn == 1 and r2.fp == 1


def test_multi_location_case_matches_either_end():
    # A cross-file case with two acceptable locations matches a finding at EITHER.
    case = {
        "id": "cross-file-key-mismatch",
        "locations": [
            {"file": "src/summary.py", "line": 14},
            {"file": "src/ingest.py", "line": 16},
        ],
        "should_flag": True,
        "requires_integration_pass": True,
    }
    at_consumer = _f("src/summary.py", 14, "cross-file-key-mismatch")
    at_producer = _f("src/ingest.py", 16, "cross-file-key-mismatch")
    elsewhere = _f("src/orders.py", 99, "cross-file-key-mismatch")
    assert metrics.match(at_consumer, case, TOL)
    assert metrics.match(at_producer, case, TOL)
    assert not metrics.match(elsewhere, case, TOL)


def test_suffix_path_matching():
    # Model reports bare filename; still matches src/orders.py.
    findings = [_f("orders.py", 24)]
    r = metrics.score(findings, CASES, tolerance=TOL)
    assert r.tp == 1


def test_format_report_contains_both_numbers():
    baseline = metrics.score([_f("src/settings.py", 10, "broad-except")], CASES, tolerance=TOL)
    enriched = metrics.score([_f("src/orders.py", 24)], CASES, tolerance=TOL)
    report = metrics.format_report(baseline, enriched)
    assert "precision" in report
    assert f"{baseline.precision:.3f}" in report
    assert f"{enriched.precision:.3f}" in report
    assert "cross-file-key-mismatch" in report  # known gap surfaced


def test_empty_findings_empty_positives_precision_one():
    # A clean sub-diff: no findings, only a should_flag=false case.
    neg_only = [CASES[1]]
    r = metrics.score([], neg_only, tolerance=TOL)
    assert r.precision == 1.0 and r.recall == 1.0
