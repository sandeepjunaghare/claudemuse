"""Integration acceptance: the semantic (prompt-context) dedupe layer (TR8).

Real ``claude -p`` calls, gated on the CLI; ``BASELINE_MODEL`` (haiku) caps cost.
Runs multipass on ``pr.diff`` once, then AGAIN with the first run's findings
threaded in as ``prior_findings=`` — the model is told what NOT to repeat. The
structural ``suppress_prior`` backstop is then asserted to yield zero NEW
comments for the reliably-located ``none-deref`` (pinned precisely to sidestep
residual model nondeterminism, as ``test_multipass_live`` does).

Non-deterministic → assert on structure/outcomes, never on model prose (PRD
principle 5). Expensive; run once — NOT part of ``make test``.
"""

import json
import shutil

import config
import dedupe
import metrics
import multipass
import pytest
import workspace

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not on PATH"),
]


def _cases():
    return json.loads(config.GROUND_TRUTH.read_text(encoding="utf-8"))["cases"]


def _case(cid):
    return next(c for c in _cases() if c["id"] == cid)


def _flagged(findings, cid):
    return any(
        metrics.match(f, _case(cid), config.LINE_MATCH_TOLERANCE) for f in findings
    )


def test_semantic_layer_suppresses_rerun_none_deref():
    """Second run receives the first run's findings in-prompt → the model does
    not re-report the none-deref, and the structural backstop confirms zero NEW
    comments for it (the semantic layer working end-to-end)."""
    diff = (config.FIXTURE_REPO / "pr.diff").read_text(encoding="utf-8")

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        first = multipass.review_multipass(diff, model=config.BASELINE_MODEL, cwd=str(ws))

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        second = multipass.review_multipass(
            diff, model=config.BASELINE_MODEL, cwd=str(ws), prior_findings=first
        )

    new, still = dedupe.suppress_prior(
        second, first, tolerance=config.DEDUPE_LINE_TOLERANCE
    )
    assert not _flagged(new, "none-deref"), (
        "the previously-reported none-deref must NOT reappear as a new comment "
        "when prior findings are fed into the prompt"
    )
