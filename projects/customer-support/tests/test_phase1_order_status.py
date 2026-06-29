"""Phase 1 integration tests: order-status resolution end-to-end (live API).

Ground truth is tool calls and outcomes, NOT the model's wording (spec Validation
Strategy). These assert on `tool_calls` membership/ordering and the terminal
`ResultMessage` outcome — with a single lenient substring check on the answer as a
resolution signal.
"""

import shutil

import pytest

import config

# The Agent SDK runs the `claude` CLI subprocess, which authenticates via the
# user's Claude Code login OR ANTHROPIC_API_KEY. Skip only if neither exists.
_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _runnable, reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run."),
]


@pytest.mark.asyncio
async def test_order_status_resolves_end_to_end(run_agent):
    """Happy path: verify identity, then look up the order, then answer."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of my order O1001?"
    )

    # Tool selection + chaining: identity verified before the order is fetched.
    assert "get_customer" in run.tool_calls, run.tool_calls
    assert "lookup_order" in run.tool_calls, run.tool_calls
    assert run.tool_calls.index("get_customer") < run.tool_calls.index("lookup_order"), run.tool_calls

    # Terminal outcome (TR1): finished on a successful ResultMessage.
    assert run.terminated_by_result is True
    assert run.subtype == "success", run.subtype
    assert run.is_error is False

    # Lenient resolution signal — not an assertion on phrasing.
    assert "ship" in run.final_text.lower(), run.final_text


@pytest.mark.asyncio
async def test_loop_terminates_on_completion_not_cap(run_agent):
    """TR1 anti-pattern guard: the run ends on completion, not by hitting max_turns."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of my order O1001?"
    )
    assert run.terminated_by_result is True
    assert run.terminated_by_cap is False, run.subtype
    assert (run.num_turns or 0) < 20  # well under the backstop


@pytest.mark.asyncio
async def test_identification_by_email_only(run_agent):
    """A customer identified by email (not name) should still verify then look up."""
    run = await run_agent(
        "This is alice@example.com — can you check the status of order O1003 for me?"
    )
    assert "get_customer" in run.tool_calls, run.tool_calls
    assert "lookup_order" in run.tool_calls, run.tool_calls
    assert run.tool_calls.index("get_customer") < run.tool_calls.index("lookup_order"), run.tool_calls
    assert run.subtype == "success", run.subtype


@pytest.mark.asyncio
async def test_uses_lookup_order_not_second_get_customer(run_agent):
    """Disambiguation: the order is fetched via lookup_order, not a second get_customer."""
    run = await run_agent(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of my order O1001?"
    )
    assert run.tool_calls.count("get_customer") >= 1
    assert "lookup_order" in run.tool_calls
    # The order detail came from lookup_order, demonstrating the two similar tools
    # are distinguished by description.
    assert run.tool_calls.count("lookup_order") >= 1, run.tool_calls
