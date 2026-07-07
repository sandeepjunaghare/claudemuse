"""Offline tests for the pure structural dedupe (TR8/FR3).

Hand-authored ``Finding`` lists; no CLI. This is the deterministic guarantee
behind "a second commit produces zero duplicate comments" — treat a failure as a
correctness bug. Identity is ``detected_pattern`` (controlled slug), never
``issue`` prose.
"""

import dedupe
import pytest
from parse import Finding, Location

TOL = 3


def _f(file, line, pattern="none-deref", severity="high", issue="x"):
    return Finding(
        location=Location(file, line),
        issue=issue,
        severity=severity,
        suggested_fix="fix",
        detected_pattern=pattern,
        category="correctness",
    )


# --- is_duplicate ------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [
        # same file + pattern, within tolerance → dupe
        (_f("src/orders.py", 24), _f("src/orders.py", 26), True),
        # same file + pattern, line diff > tolerance → not
        (_f("src/orders.py", 24), _f("src/orders.py", 40), False),
        # same file + line, different pattern → not
        (_f("src/orders.py", 24, "none-deref"), _f("src/orders.py", 24, "off-by-one"), False),
        # suffix path forms still match (orders.py vs src/orders.py)
        (_f("orders.py", 24), _f("src/orders.py", 25), True),
        # different files → not
        (_f("src/orders.py", 24), _f("src/summary.py", 24), False),
    ],
)
def test_is_duplicate(a, b, expected):
    assert dedupe.is_duplicate(a, b, TOL) is expected


def test_empty_pattern_fallback_file_line_only():
    # Two blank-pattern findings dupe only on file + line-within-tolerance.
    a = _f("src/x.py", 10, pattern="")
    b = _f("src/x.py", 11, pattern="")
    c = _f("src/x.py", 40, pattern="")
    assert dedupe.is_duplicate(a, b, TOL) is True
    assert dedupe.is_duplicate(a, c, TOL) is False
    # A blank pattern never collapses into a slugged one at the same spot unless
    # file+line match — but it must not merge two DIFFERENT slugs. (Blank vs slug
    # falls back to file+line, which is acceptable per the documented contract.)
    blank = _f("src/x.py", 10, pattern="")
    slug = _f("src/x.py", 10, pattern="none-deref")
    assert dedupe.is_duplicate(blank, slug, TOL) is True  # file+line coincide


# --- dedupe (within-run) -----------------------------------------------------


def test_dedupe_collapses_within_run_keep_first():
    first = _f("src/orders.py", 24, issue="from integration")
    second = _f("src/orders.py", 25, issue="from per-file")
    distinct = _f("src/summary.py", 14, "cross-file-key-mismatch")
    out = dedupe.dedupe([first, second, distinct], tolerance=TOL)
    assert len(out) == 2
    # keep-first: the integration report (placed first) survives
    kept = next(f for f in out if f.detected_pattern == "none-deref")
    assert kept.issue == "from integration"
    assert any(f.detected_pattern == "cross-file-key-mismatch" for f in out)


def test_dedupe_leaves_distinct_findings_untouched():
    a = _f("src/orders.py", 24, "none-deref")
    b = _f("src/summary.py", 14, "cross-file-key-mismatch")
    out = dedupe.dedupe([a, b], tolerance=TOL)
    assert len(out) == 2


def test_dedupe_does_not_mutate_input():
    findings = [_f("src/orders.py", 24), _f("src/orders.py", 25)]
    original = list(findings)
    dedupe.dedupe(findings, tolerance=TOL)
    assert findings == original  # inputs unchanged (pure)


# --- suppress_prior (cross-run) ----------------------------------------------


def test_suppress_prior_zero_duplicates_when_all_reported():
    """The headline TR8 assertion: a re-run whose only finding was already
    reported yields zero NEW comments."""
    current = [_f("src/orders.py", 24)]
    prior = [_f("src/orders.py", 25)]  # same issue, drifted line, prior run
    new, still = dedupe.suppress_prior(current, prior, tolerance=TOL)
    assert new == []  # zero duplicate comments
    assert len(still) == 1  # tracked as still-unresolved


def test_suppress_prior_surfaces_genuinely_new():
    current = [_f("src/orders.py", 24, "none-deref"), _f("src/summary.py", 14, "cross-file-key-mismatch")]
    prior = [_f("src/orders.py", 24, "none-deref")]  # only the none-deref was seen before
    new, still = dedupe.suppress_prior(current, prior, tolerance=TOL)
    assert [f.detected_pattern for f in new] == ["cross-file-key-mismatch"]
    assert [f.detected_pattern for f in still] == ["none-deref"]


def test_suppress_prior_empty_prior_is_all_new():
    current = [_f("src/orders.py", 24)]
    new, still = dedupe.suppress_prior(current, [], tolerance=TOL)
    assert len(new) == 1 and still == []


def test_suppress_prior_does_not_mutate_inputs():
    current = [_f("src/orders.py", 24)]
    prior = [_f("src/orders.py", 24)]
    c0, p0 = list(current), list(prior)
    dedupe.suppress_prior(current, prior, tolerance=TOL)
    assert current == c0 and prior == p0


# --- render_prior_findings (semantic dedupe layer, Phase 4) ------------------


def test_render_prior_findings_empty_is_sentinel():
    text = dedupe.render_prior_findings([])
    assert "first review" in text


def test_render_prior_findings_lists_each_with_stable_order():
    # Deliberately out-of-order input; output must sort by (file, line).
    findings = [
        _f("src/summary.py", 14, "cross-file-key-mismatch"),
        _f("src/orders.py", 24, "none-deref"),
    ]
    text = dedupe.render_prior_findings(findings)
    # each finding's file, line, and slug appear
    assert "src/orders.py:24" in text
    assert "src/summary.py:14" in text
    assert "none-deref" in text
    assert "cross-file-key-mismatch" in text
    # stable ordering regardless of input order (orders.py sorts before summary.py)
    assert text.index("src/orders.py") < text.index("src/summary.py")
    # order-independence: shuffling the input yields the same text
    assert dedupe.render_prior_findings(list(reversed(findings))) == text
