"""Deterministic proof of the TR8 handoff_gate hook (no API).

The gate denies an incomplete/invalid-enum handoff (naming the gaps) and allows a
complete one. On allow it best-effort verified-stamps `customer.verified` from the
process-global `verified_store` (Task 0: updatedInput reaches the in-process tool).
"""

import asyncio

from hooks import verified_store
from hooks.handoff_gate import handoff_gate

_TOOL = "mcp__support__escalate_to_human"

_COMPLETE = {
    "reason_for_escalation": "explicit_request",
    "root_cause": "Customer demanded a manager.",
    "recommended_action": "Call back within 1 hour.",
    "actions_taken": [],
    "customer": {"id": "C001"},
}


def _run(tool_input, session_id="s"):
    return asyncio.run(
        handoff_gate(
            {"tool_name": _TOOL, "tool_input": tool_input, "session_id": session_id},
            "tu",
            {"signal": None},
        )
    )


def _decision(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


def test_complete_handoff_allowed():
    """A complete handoff is not denied."""
    assert _decision(_run(_COMPLETE)) != "deny"


def test_incomplete_handoff_denied():
    """A handoff missing required fields is denied."""
    result = _run({"reason_for_escalation": "explicit_request"})
    assert _decision(result) == "deny"


def test_deny_reason_names_missing_fields():
    """The deny reason lists the exact missing fields so the retry succeeds in one hop."""
    result = _run({"reason_for_escalation": "explicit_request"})
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "root_cause" in reason
    assert "recommended_action" in reason
    assert "escalate_to_human" in reason


def test_bad_enum_denied():
    """An invalid reason_for_escalation is denied as invalid."""
    result = _run({**_COMPLETE, "reason_for_escalation": "banana"})
    assert _decision(result) == "deny"
    assert "reason_for_escalation(invalid)" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_non_escalate_tool_ignored():
    """The gate only acts on escalate_to_human; other tools pass through."""
    assert handoff_gate is not None
    result = asyncio.run(
        handoff_gate(
            {"tool_name": "mcp__support__lookup_order", "tool_input": {}, "session_id": "s"},
            "tu",
            {"signal": None},
        )
    )
    assert result == {}


def test_verified_stamp_false_when_unverified():
    """On allow, an unverified customer is stamped verified=False (code-backed fact)."""
    result = _run(_COMPLETE, session_id="s_unverified")
    stamped = result["hookSpecificOutput"]["updatedInput"]["customer"]["verified"]
    assert stamped is False


def test_verified_stamp_true_when_verified():
    """On allow, a customer verified in the session is stamped verified=True."""
    verified_store.mark_verified("s_verified", "C001")
    result = _run(_COMPLETE, session_id="s_verified")
    stamped = result["hookSpecificOutput"]["updatedInput"]["customer"]["verified"]
    assert stamped is True
