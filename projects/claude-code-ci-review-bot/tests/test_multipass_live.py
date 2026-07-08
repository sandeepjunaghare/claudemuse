"""Integration acceptance demos for multipass + dedupe (TR6/TR7/TR8/FR3).

Real ``claude -p`` calls, gated on the CLI being available; ``BASELINE_MODEL``
(haiku) caps cost. Non-deterministic → every assert is on structure/outcomes
(matched cases, presence in new/still), NEVER on model prose (PRD principle 5).

If the integration pass doesn't reliably catch the cross-file bug on haiku, the
fix is to iterate ``review-integration.md`` wording (the fixture/prompt is ground
truth), or run that one pass on sonnet — never loosen an assert.
"""

import json
import shutil

import pytest

import config
import dedupe
import metrics
import multipass
import store
import workspace

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


def _flagged(findings, cid):
    return any(
        metrics.match(f, _case(cid), config.LINE_MATCH_TOLERANCE) for f in findings
    )


def _pr_diff():
    return (config.FIXTURE_REPO / "pr.diff").read_text(encoding="utf-8")


def test_per_file_isolation_misses_cross_file():
    """Per-file passes review each file alone → cannot see the cross-file bug,
    but DO catch the same-file none-deref (TR6/TR7)."""
    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        findings = multipass.review_per_file(
            _pr_diff(), config.ENRICHED_PROMPT, config.BASELINE_MODEL, cwd=str(ws)
        )
    assert not _flagged(findings, "cross-file-key-mismatch"), (
        "per-file isolation must NOT catch the cross-file key mismatch"
    )
    assert _flagged(findings, "none-deref"), "per-file must catch the same-file none-deref"


def test_integration_pass_catches_cross_file():
    """The whole-diff integration pass catches the cross-file key mismatch (TR6).
    Combined with the per-file miss above → caught ONLY by the integration pass."""
    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        findings = multipass.review_integration(
            _pr_diff(), config.INTEGRATION_PROMPT, config.BASELINE_MODEL, cwd=str(ws)
        )
    assert _flagged(findings, "cross-file-key-mismatch"), (
        "integration pass must catch the cross-file key mismatch"
    )


def test_multipass_scores_clean():
    """Merged multipass result: cross-file + none-deref are TPs (single_pass=False),
    the convention-dependent case is NOT flagged (CLAUDE.md present) → no FP, and
    each matched pattern appears once (no contradictory findings)."""
    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        findings = multipass.review_multipass(
            _pr_diff(), model=config.BASELINE_MODEL, cwd=str(ws)
        )
    result = metrics.score(
        findings, _cases(), tolerance=config.LINE_MATCH_TOLERANCE, single_pass=False
    )
    assert "cross-file-key-mismatch" in result.matched  # now a real TP
    assert "none-deref" in result.matched
    assert not _flagged(findings, "settings-broad-except"), (
        "convention-dependent case must NOT be flagged with CLAUDE.md present"
    )
    # no contradictory / duplicate findings: each matched pattern once
    patterns = [f.detected_pattern for f in findings]
    assert patterns.count("cross-file-key-mismatch") == 1
    assert patterns.count("none-deref") == 1


def test_dedupe_across_reruns_zero_duplicates(tmp_path):
    """Re-running multipass on the same PR yields zero duplicate comments for the
    previously-reported none-deref (TR8/FR3). Asserts on none-deref specifically
    (reliably caught in both runs) for robustness against nondeterminism."""
    diff = _pr_diff()
    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        first = multipass.review_multipass(diff, model=config.BASELINE_MODEL, cwd=str(ws))
    store.save_findings("test-live", first, base_dir=tmp_path)

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        second = multipass.review_multipass(diff, model=config.BASELINE_MODEL, cwd=str(ws))

    prior = store.load_prior("test-live", base_dir=tmp_path)
    new, still = dedupe.suppress_prior(
        second, prior, tolerance=config.DEDUPE_LINE_TOLERANCE
    )
    assert not _flagged(new, "none-deref"), (
        "the previously-reported none-deref must NOT reappear as a new comment"
    )
    assert _flagged(still, "none-deref"), (
        "the none-deref should be tracked as still-unresolved (suppressed dup)"
    )
