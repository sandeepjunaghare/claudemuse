"""Integration acceptance demos (TR3/TR4/TR5) — real ``claude -p`` reviews.

Gated on the CLI being available; uses the cheap ``BASELINE_MODEL`` (haiku) to
cap cost. These calls are non-deterministic, so every assert is on
structure/direction/outcomes (matched cases, precision inequality, label
equality) — NEVER on the model's prose (PRD principle 5).

If the TR3/precision deltas don't reproduce cleanly, the fix is to iterate the
fixture (``pricing.py`` + fixture ``CLAUDE.md`` wording), not to loosen asserts —
the fixture is ground truth and calibrating it is the precision work.
"""

import json
import shutil

import pytest

import config
import metrics

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("claude") is None,
        reason="claude CLI not on PATH",
    ),
]


def _cases():
    return json.loads(config.GROUND_TRUTH.read_text(encoding="utf-8"))["cases"]


def _case(cid):
    return next(c for c in _cases() if c["id"] == cid)


def _convention_case():
    """The should_flag=false single-pass case (correct only under CLAUDE.md)."""
    return next(
        c
        for c in _cases()
        if not c.get("should_flag") and not c.get("requires_integration_pass")
    )


def _flagged(findings, cid):
    case = _case(cid)
    return any(metrics.match(f, case, config.LINE_MATCH_TOLERANCE) for f in findings)


def _flagged_case(findings, case):
    return any(metrics.match(f, case, config.LINE_MATCH_TOLERANCE) for f in findings)


def test_real_bug_flagged_idiom_not_flagged():
    """Enriched + CLAUDE.md present: flag the none-deref, stay silent on the
    convention-dependent case (broad-except by policy)."""
    findings = metrics.run_variant(
        config.ENRICHED_PROMPT, config.BASELINE_MODEL, include_claude_md=True
    )
    assert _flagged(findings, "none-deref"), "genuine bug must be flagged"
    assert not _flagged_case(findings, _convention_case()), (
        "convention-dependent code must NOT be flagged when CLAUDE.md present"
    )


def test_precision_improves_before_to_after():
    """baseline vs enriched prompt (CLAUDE.md present in both): enriched
    precision must not regress. Records both to data/metrics/."""
    result = metrics.run_metrics()
    baseline, enriched = result["baseline"], result["enriched"]
    assert enriched.precision >= baseline.precision
    # persisted for the headline trust metric
    assert (config.METRICS_DIR / "baseline.json").exists()
    assert (config.METRICS_DIR / "enriched.json").exists()


def test_tr3_behavior_change_present_vs_absent():
    """Enriched prompt, CLAUDE.md present vs absent: the convention-dependent case
    (broad-except by policy) is flagged with it ABSENT and not flagged with it
    PRESENT (the TR3 delta)."""
    result = metrics.run_tr3_demo()
    assert result["absent_flagged"], (
        "without the fixture CLAUDE.md policy, the model should flag the broad "
        "`except Exception` in settings access as error-swallowing"
    )
    assert not result["present_flagged"], (
        "with the CLAUDE.md 'settings reads must be total' policy present, it "
        "must not be flagged"
    )


def test_severity_consistent_across_two_prs():
    """The none-deref class gets the SAME severity label in pr.diff and
    pr-02.diff (guaranteed by apply_canonical_severity)."""
    f1 = metrics.run_variant(
        config.ENRICHED_PROMPT,
        config.BASELINE_MODEL,
        include_claude_md=True,
        diff_name="pr.diff",
    )
    f2 = metrics.run_variant(
        config.ENRICHED_PROMPT,
        config.BASELINE_MODEL,
        include_claude_md=True,
        diff_name="pr-02.diff",
    )
    sev1 = _severity_of(f1, "none-deref", "src/orders.py")
    sev2 = _severity_of(f2, "none-deref", "src/accounts.py")
    assert sev1 is not None, "none-deref not found in pr.diff review"
    assert sev2 is not None, "none-deref not found in pr-02.diff review"
    assert sev1 == sev2


def _severity_of(findings, pattern, file_suffix):
    for f in findings:
        if f.detected_pattern == pattern and f.location.file.endswith(
            file_suffix.split("/")[-1]
        ):
            return f.severity
    # fall back: any finding with that pattern
    for f in findings:
        if f.detected_pattern == pattern:
            return f.severity
    return None


def test_cross_file_is_a_known_gap_not_penalized(capsys):
    """The cross-file key mismatch is a Phase-2 *known gap*: excluded from
    single-pass recall and, if opportunistically caught by the whole-diff pass,
    NOT penalized as a false positive.

    NOTE (deviation from the plan's premise): the plan assumed a single pass
    would MISS the cross-file bug. Empirically, because ``pr.diff`` bundles all
    files into one review, the whole-diff pass has cross-file visibility and a
    capable model can connect ``"user_id"`` / ``"userId"``. Per-file *isolation*
    (Phase-3 TR6 local passes) is what genuinely can't see across files; reliable
    cross-file detection is Phase-3's integration pass. So we assert the
    deterministic metric invariant (known gap, precision-neutral either way) and
    just record whether this run caught it — never a flaky "must miss" assert.
    """
    findings = metrics.run_variant(
        config.ENRICHED_PROMPT, config.BASELINE_MODEL, include_claude_md=True
    )
    result = metrics.score(
        findings, _cases(), tolerance=config.LINE_MATCH_TOLERANCE, single_pass=True
    )
    # Excluded from recall regardless of catch.
    assert "cross-file-key-mismatch" in result.known_gaps
    assert "cross-file-key-mismatch" not in result.missed
    # A catch is a bonus, never an FP against the cross-file case.
    caught = _flagged(findings, "cross-file-key-mismatch")
    if caught:
        assert "cross-file-key-mismatch" in result.known_gap_hits
    print(f"single-pass caught cross-file bug: {caught}")
