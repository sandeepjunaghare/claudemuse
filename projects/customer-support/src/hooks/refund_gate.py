"""Refund-limit guardrail (TR3): a PreToolUse hook that DENIES any
`process_refund` over the policy limit before the tool can execute.

This deny is the deterministic, 100%-provable invariant — no large refund is
ever issued autonomously, regardless of what the model decides. The deny reason
is phrased as a routing instruction so the model's calibrated response is to
escalate. The limit comes from `config.REFUND_POLICY_LIMIT` (never hardcoded).
"""

import config


async def refund_gate(input: dict, tool_use_id, context) -> dict:
    """Deny over-limit refunds, routing them to escalation (TR3)."""
    # Defensive tool-name check — correctness must not depend on matcher semantics.
    if not input.get("tool_name", "").endswith("process_refund"):
        return {}

    amount = input.get("tool_input", {}).get("amount")
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0

    # Strictly OVER the limit is blocked; exactly at the limit is within policy.
    if amount <= config.REFUND_POLICY_LIMIT:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Refund of ${amount:,.2f} exceeds the ${config.REFUND_POLICY_LIMIT:,.2f} "
                "policy limit and cannot be issued automatically. Do NOT retry this refund. "
                "Escalate it to a human via escalate_to_human, including the customer, order, "
                "amount, and reason."
            ),
        }
    }
