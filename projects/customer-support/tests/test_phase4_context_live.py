"""Phase 4 integration tests: multi-turn context hygiene + multi-issue (live API).

The hard TR9a guarantees (store/recorder/inject, incl. the simulated-`/compact`
proof) and the TR9b trim are proven deterministically in the unit suites. These
live tests confirm the end-to-end model-driven behavior over a PERSISTENT session:
case facts recalled verbatim after a multi-turn exchange (FR6/TR9), venting
handled with calibration then escalated on a reiterated human request (TR7
carry-forward), and a multi-issue message resolved in one unified reply (FR5).
Assertions target tool calls / outcomes, with at most a lenient prose substring.
"""

import shutil

import pytest

import config

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _runnable, reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run."),
]


async def test_multiturn_case_facts_recall(run_conversation):
    """TR9/FR6: exact order id + amount survive a multi-turn exchange (injected block)."""
    run = await run_conversation([
        "Hi, I'm Alice Wong, alice@example.com — what's the status of order O1001?",
        "Thanks. Before I go — remind me the exact amount and the order number we discussed.",
    ])
    # Turn 1 verified the customer and looked up the order.
    assert "get_customer" in run.turns[0].tool_calls, run.turns[0].tool_calls
    assert "lookup_order" in run.turns[0].tool_calls, run.turns[0].tool_calls
    # Turn 2 recalls the verbatim figures carried by the injected case-facts block.
    t2 = run.turns[1].final_text
    assert "O1001" in t2, t2
    assert "42" in t2, t2
    assert run.turns[1].terminated_by_cap is False, run.turns[1].subtype


async def test_venting_then_reiteration_escalates(run_conversation):
    """TR7 carry-forward: turn 1 venting -> acknowledge + resolve (no escalation);
    turn 2 reiterated human demand -> escalate."""
    run = await run_conversation([
        "I'm Alice Wong (alice@example.com). This is the THIRD time order O1001 is late and I'm furious.",
        "Forget it — just get me a human, now.",
    ])
    # Turn 1: tried to resolve (looked up the order), did NOT escalate on tone alone.
    assert "lookup_order" in run.turns[0].tool_calls, run.turns[0].tool_calls
    assert "escalate_to_human" not in run.turns[0].tool_calls, run.turns[0].tool_calls
    # Turn 2: explicit reiterated request -> escalate.
    assert "escalate_to_human" in run.turns[1].tool_calls, run.turns[1].tool_calls
    assert run.turns[1].terminated_by_cap is False, run.turns[1].subtype


async def test_multi_issue_unified_reply(run_conversation):
    """FR5: a two-request message resolves BOTH (status + in-policy refund) in one turn."""
    run = await run_conversation([
        "I'm Alice Wong (alice@example.com). Where is order O1001, and please refund $30 of it for a damaged item.",
    ])
    turn = run.turns[0]
    # Both tool chains fire within the single turn.
    assert "get_customer" in turn.tool_calls, turn.tool_calls
    assert "lookup_order" in turn.tool_calls, turn.tool_calls
    assert "process_refund" in turn.tool_calls, turn.tool_calls
    assert turn.subtype == "success", turn.subtype
    assert turn.terminated_by_cap is False, turn.subtype
    # The unified reply references both the status and the refund (lenient).
    low = turn.final_text.lower()
    assert "refund" in low, turn.final_text
    assert ("ship" in low or "status" in low or "o1001" in low), turn.final_text
