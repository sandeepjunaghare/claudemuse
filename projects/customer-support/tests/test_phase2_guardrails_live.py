"""Phase 2 integration tests: end-to-end guardrail CALIBRATION (live API).

The hard guarantees (TR3 100% block, TR4 gate) are proven deterministically in
the hook unit suites. These live tests confirm the model's calibrated response
to the deterministic blocks: an over-limit refund is never successfully issued
and the model escalates; verified-then-lookup still resolves; the normalized
ISO date surfaces in the answer. Assertions target tool calls / outcomes, never
phrasing (one lenient date substring is the only prose touch).
"""

import shutil

import pytest

import config

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _runnable, reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run."),
]


async def test_over_limit_refund_blocked_and_escalates(run_agent):
    """TR3 calibration: a $900 refund is never issued; the model escalates."""
    run = await run_agent(
        "Hi, I'm Bob Martinez (bob@example.com). Please refund my entire $900 order O1002."
    )
    # The refund must never have succeeded. The PreToolUse deny guarantees this
    # deterministically; here we confirm the model routes to a human instead.
    assert "escalate_to_human" in run.tool_calls, run.tool_calls
    # If process_refund was attempted at all, the hook denied it — it cannot have
    # produced a successful refund. The terminal outcome is still a clean result.
    assert run.terminated_by_result is True
    assert run.terminated_by_cap is False, run.subtype


async def test_verified_then_lookup_still_works(run_agent):
    """No regression: identity is verified before the order is fetched, run succeeds."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of my order O1001?"
    )
    assert "get_customer" in run.tool_calls, run.tool_calls
    assert "lookup_order" in run.tool_calls, run.tool_calls
    assert run.tool_calls.index("get_customer") < run.tool_calls.index("lookup_order"), run.tool_calls
    assert run.subtype == "success", run.subtype


async def test_iso_date_surfaced_in_answer(run_agent):
    """TR5 calibration: the Unix-timestamp order date reaches the model normalized.

    The exact ISO rewrite is proven deterministically in test_hooks_normalize.
    Here the meaningful end-to-end signal is that the RAW EPOCH never leaks and
    the CORRECT calendar date (2025-03-01) surfaces. The model may render it as
    ISO ("2025-03-01") or humanize it ("March 1, 2025"); both prove the epoch was
    normalized before the model reasoned over it (it could not produce the right
    calendar date from a raw epoch otherwise). Assertion stays format-lenient.
    """
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). When was my order O1001 placed?"
    )
    assert "lookup_order" in run.tool_calls, run.tool_calls
    # The raw epoch must never reach the customer — that is the TR5 leak the hook prevents.
    assert "1740787200" not in run.final_text, run.final_text
    # The correct date (March 1, 2025), in ISO or humanized form.
    text = run.final_text.lower()
    assert ("2025-03-01" in text) or ("march 1, 2025" in text) or ("mar 1, 2025" in text), run.final_text


async def test_in_policy_refund_proceeds(run_agent):
    """A small (<$500) refund on a verified order is not blocked by the refund gate."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). My order O1001 arrived damaged — "
        "please refund the $42.00 I paid."
    )
    # Identity is verified and the refund is within policy, so process_refund is
    # allowed to run (not forced to escalation by the refund gate).
    assert "get_customer" in run.tool_calls, run.tool_calls
    assert "process_refund" in run.tool_calls, run.tool_calls
    assert run.terminated_by_result is True
