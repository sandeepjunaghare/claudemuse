"""Prerequisite identity gate (TR4): `lookup_order` and `process_refund` may
only run against a `customer_id` that was VERIFIED this session — where verified
means a prior `get_customer` resolved to EXACTLY ONE customer.

Two hooks cooperate via `verified_store`:
- `record_verified_customer` (PostToolUse on `get_customer`) — the WRITER. Marks
  a customer verified only on a single match.
- `prerequisite_gate` (PreToolUse on `lookup_order`/`process_refund`) — the
  READER. Denies the call unless its `customer_id` is verified for the session.

OBSERVED tool_response SHAPE (Task 0 — do NOT re-guess): the PostToolUse hook
receives `tool_response` as the BARE content list, e.g.
`[{"type": "text", "text": "Verified customer Alice Wong (id C001)."}]`.
`structuredContent` (the tool's matchCount/matches) is DROPPED by the SDK before
it reaches any hook (`claude_agent_sdk/_internal/query.py:645-693`). So the
single-match id is recovered from the text, whose verified sentence
`"Verified customer <name> (id C###)."` is uniquely emitted only on a single
match (multi-match -> "Found N customers ..."; zero -> "No customer found ..."),
so neither of those verifies — preserving the TR7 disambiguation path.
"""

import re

from hooks import verified_store

#: Matches ONLY the single-match sentinel `get_customer` emits (tools/server.py:81).
#: Multi-match and zero-match texts don't contain `(id C###)`, so they never verify.
_VERIFIED_ID_RE = re.compile(r"Verified customer .*\(id\s+(?P<id>[A-Za-z0-9]+)\)")


def _extract_text(tool_response) -> str:
    """Join the text of a bare content list (the Task-0 tool_response shape)."""
    if not isinstance(tool_response, list):
        return ""
    return " ".join(
        item.get("text", "")
        for item in tool_response
        if isinstance(item, dict) and item.get("type") == "text"
    )


async def record_verified_customer(input: dict, tool_use_id, context) -> dict:
    """PostToolUse writer: mark the customer verified on a SINGLE match (TR4).

    Never blocks or rewrites — always returns ``{}``.
    """
    if not input.get("tool_name", "").endswith("get_customer"):
        return {}

    text = _extract_text(input.get("tool_response"))
    match = _VERIFIED_ID_RE.search(text)
    if match:
        verified_store.mark_verified(input.get("session_id", ""), match.group("id"))
    return {}


async def prerequisite_gate(input: dict, tool_use_id, context) -> dict:
    """PreToolUse gate: deny order/refund actions on an unverified customer (TR4)."""
    tool_name = input.get("tool_name", "")
    if not (tool_name.endswith("lookup_order") or tool_name.endswith("process_refund")):
        return {}

    session_id = input.get("session_id", "")
    customer_id = input.get("tool_input", {}).get("customer_id")

    if customer_id and verified_store.is_verified(session_id, customer_id):
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Customer identity is not verified for this action. Call get_customer "
                "first and obtain a SINGLE matching customer (a verified customer id) "
                "before looking up orders or issuing refunds. If get_customer returns "
                "multiple matches, ask the customer for an additional identifier instead "
                "of guessing."
            ),
        }
    }
