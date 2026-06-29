"""Handoff completeness gate (TR8): a PreToolUse hook on `escalate_to_human`.

This is the DETERMINISTIC half of TR8. The model fills the enriched
`escalate_to_human` schema; this hook calls `handoff.missing_fields` and DENIES
the call when any required field is absent/empty or `reason_for_escalation` is not
in the enum — the deny reason names the exact gaps and tells the model to re-call
with them filled. Same deny→retry mechanism proven for TR3/TR4 in Phase 2; the
`max_turns` backstop bounds the retries. A complete handoff is allowed through.

Task 0 finding (verified this phase): `updatedInput` from a PreToolUse hook DOES
mutate the input an in-process MCP tool receives (smoke-confirmed — the injected
field reached the tool). So the optional verified-stamp below is live: on allow,
we overwrite `customer.verified` with the code-backed fact from `verified_store`,
so the handoff's verified flag is authoritative rather than a model claim. This is
best-effort — if no verified id is resolvable, the model-provided value stands and
the completeness guarantee (the deny) is unaffected.
"""

import handoff
from hooks import verified_store


def _customer_id(tool_input: dict):
    """Customer id from nested `customer.id` or flat `customer_id` (mirror handoff)."""
    customer = tool_input.get("customer")
    if isinstance(customer, dict) and customer.get("id"):
        return customer.get("id")
    return tool_input.get("customer_id")


async def handoff_gate(input: dict, tool_use_id, context) -> dict:
    """Deny incomplete/invalid handoffs; allow (and verified-stamp) complete ones (TR8)."""
    # Defensive tool-name check — correctness must not depend on matcher semantics.
    if not input.get("tool_name", "").endswith("escalate_to_human"):
        return {}

    tool_input = input.get("tool_input", {})
    missing = handoff.missing_fields(tool_input)
    if missing:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "The handoff to a human is incomplete — the following field(s) are "
                    f"missing or invalid: {', '.join(missing)}. The human cannot see the "
                    "conversation, so re-call escalate_to_human with every field filled: "
                    "reason_for_escalation (one of "
                    f"{', '.join(handoff.REASON_VALUES)}), root_cause, recommended_action, "
                    "actions_taken (a list, may be empty), and customer.id."
                ),
            }
        }

    # Allowed. Best-effort verified-stamp from the code-backed store (Task 0: the
    # updatedInput mutation reaches the tool). Only stamp when we can resolve the id;
    # never block on this — the completeness guarantee above is the actual TR8 invariant.
    customer_id = _customer_id(tool_input)
    if customer_id:
        verified = verified_store.is_verified(input.get("session_id", ""), customer_id)
        new_input = dict(tool_input)
        customer = dict(new_input.get("customer") or {})
        customer.setdefault("id", customer_id)
        customer["verified"] = verified
        new_input["customer"] = customer
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": new_input,
            }
        }

    return {}
