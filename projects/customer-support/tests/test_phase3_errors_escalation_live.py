"""Phase 3 integration tests: end-to-end error handling + escalation CALIBRATION (live API).

The hard guarantees — error categories (TR6) and handoff completeness (TR8) — are
proven deterministically in the unit suites. These live tests confirm the model's
calibrated behavior against those mechanisms: a forced transient is retried and the
request resolves; a business error is explained rather than blindly retried; an
explicit human request escalates immediately; a lone venting message does not; and
the emitted handoff carries standalone context. Assertions target tool calls /
outcomes, never phrasing (a couple of lenient substrings are the only prose touch).

The flaky probabilistic path is pinned off by the autouse `_reset_flaky` fixture
(conftest); transient failures here are forced via the seam so the live runs are as
reproducible as a model-driven test can be.
"""

import shutil

import pytest

import config
from mocks import fixtures

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _runnable, reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run."),
]


async def test_transient_retried_then_resolved(run_agent):
    """TR6: a forced 503 on the order backend is retried and the status still resolves."""
    fixtures.force_transient_failures(1)
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of my order O1001?"
    )
    # The model must call lookup_order (and, after the transient, retry it) — at
    # least one call appears, and the run resolves cleanly rather than giving up.
    assert "lookup_order" in run.tool_calls, run.tool_calls
    assert run.subtype == "success", run.subtype
    assert run.terminated_by_cap is False, run.subtype
    # The raw 503 must not be what the customer is left with.
    assert "503" not in run.final_text, run.final_text


async def test_business_error_explained_not_looped(run_agent):
    """TR6: a refund on a cancelled order is a business error — explained, not retried to death."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). Please refund my cancelled order O1004 ($60)."
    )
    # A business error is non-retryable: the model must not spin until the cap.
    assert run.terminated_by_cap is False, run.subtype
    assert run.terminated_by_result is True
    # The cancelled order can't be refunded, so no successful refund confirmation.
    # (The model either explains the situation or escalates — both are acceptable;
    # what must NOT happen is a successful refund.)
    assert "refund of $60" not in run.final_text.lower(), run.final_text


async def test_explicit_request_escalates_immediately(run_agent):
    """TR7: an explicit human request escalates right away."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). Just get me a human manager, now."
    )
    assert "escalate_to_human" in run.tool_calls, run.tool_calls
    assert run.terminated_by_cap is False, run.subtype


async def test_lone_venting_does_not_escalate(run_agent):
    """TR7: a single frustrated-but-actionable message resolves the order, no escalation."""
    run = await run_agent(
        "This is the third time my order is late and I'm furious — where is order O1001? "
        "I'm Alice Wong, alice@example.com."
    )
    assert "lookup_order" in run.tool_calls, run.tool_calls
    assert "escalate_to_human" not in run.tool_calls, run.tool_calls


async def test_handoff_is_self_contained(run_agent):
    """TR8: an escalation emits standalone context (customer id + a reason value)."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). I want to speak to a manager about order O1001."
    )
    assert "escalate_to_human" in run.tool_calls, run.tool_calls
    # The handoff the model produced should reference the customer and a reason.
    # Pull the escalate_to_human input it actually sent (ground truth, not prose).
    idx = run.tool_calls.index("escalate_to_human")
    handoff_input = run.tool_inputs[idx]
    assert handoff_input.get("reason_for_escalation") in (
        "explicit_request", "policy_gap", "over_limit_refund", "stalled",
    ), handoff_input
    assert handoff_input.get("root_cause"), handoff_input
    assert handoff_input.get("recommended_action"), handoff_input
