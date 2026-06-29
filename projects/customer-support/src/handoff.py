"""Handoff summary validation + assembly (TR8).

On escalation the agent must hand a human a SELF-CONTAINED case summary — the
human never sees the conversation transcript (FR4 / TR8). The model populates the
enriched `escalate_to_human` schema; this module is the pure, SDK-free core that
(a) checks completeness (`missing_fields`) and (b) assembles the PRD §10 shape
(`build_summary`). The deterministic completeness GUARANTEE is the `handoff_gate`
PreToolUse hook, which calls `missing_fields` and denies an incomplete handoff so
the model retries with full data — same deny→retry mechanism as TR3/TR4.

What "self-contained" means here (deliberate field-strictness choices):
- `reason_for_escalation`, `root_cause`, `recommended_action` are ALWAYS required
  and must be non-empty — a human cannot act without the why, the cause, and the
  recommendation.
- `actions_taken` is required to be PRESENT but may be an empty list: an immediate
  explicit-request escalation legitimately has no prior actions, and demanding a
  fabricated action would be worse than an honest empty list.
- Customer context: at least a customer id is required (`customer.id` or the flat
  `customer_id`) so the human knows whose case this is.
- `order` context is OPTIONAL: a pure policy-gap question may have no order.
"""

from typing import Any

#: The four legitimate escalation reasons (matches PRD §10 and the TR7 few-shots).
REASON_VALUES = ("explicit_request", "policy_gap", "over_limit_refund", "stalled")

#: Fields that must be present (and, except actions_taken, non-empty) for a
#: complete handoff. Customer-id presence is checked separately (it accepts either
#: the nested `customer.id` or a flat `customer_id`).
REQUIRED_FIELDS = ("reason_for_escalation", "root_cause", "recommended_action", "actions_taken")


def _is_empty(value: Any) -> bool:
    """True for None or an empty/whitespace string (lists are handled separately)."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _customer_id(tool_input: dict) -> Any:
    """Recover the customer id from either the nested `customer.id` or flat `customer_id`."""
    customer = tool_input.get("customer")
    if isinstance(customer, dict) and not _is_empty(customer.get("id")):
        return customer.get("id")
    return tool_input.get("customer_id")


def missing_fields(tool_input: dict) -> list[str]:
    """Return the names of required fields that are missing/empty for a handoff.

    - Each `REQUIRED_FIELDS` entry is flagged when absent or empty. `actions_taken`
      is special-cased: it must be PRESENT (a list, possibly empty) — an absent
      key is flagged, an empty list is fine.
    - `reason_for_escalation(invalid)` is appended when the reason is present but
      not one of `REASON_VALUES` (so the gate can tell "missing" from "wrong").
    - `customer.id` is flagged when neither `customer.id` nor `customer_id` is set.
    """
    missing: list[str] = []

    for field in REQUIRED_FIELDS:
        if field == "actions_taken":
            value = tool_input.get("actions_taken")
            if not isinstance(value, list):  # absent or wrong type — empty list is OK
                missing.append("actions_taken")
            continue
        if _is_empty(tool_input.get(field)):
            missing.append(field)

    reason = tool_input.get("reason_for_escalation")
    if not _is_empty(reason) and reason not in REASON_VALUES:
        missing.append("reason_for_escalation(invalid)")

    if _is_empty(_customer_id(tool_input)):
        missing.append("customer.id")

    return missing


def build_summary(tool_input: dict) -> dict[str, Any]:
    """Assemble the self-contained PRD §10 handoff summary from the tool input.

    Defensive by design: a missing optional `order` is omitted rather than faked,
    and the customer id is sourced from whichever form the model provided. Assumes
    completeness has already been enforced by `handoff_gate`, but never raises.
    """
    customer_in = tool_input.get("customer") or {}
    if not isinstance(customer_in, dict):
        customer_in = {}

    customer = {
        "id": _customer_id(tool_input),
        "name": customer_in.get("name") or tool_input.get("customer_name"),
        "verified": customer_in.get("verified"),
    }

    summary: dict[str, Any] = {
        "customer": customer,
        "root_cause": tool_input.get("root_cause"),
        "actions_taken": tool_input.get("actions_taken") or [],
        "recommended_action": tool_input.get("recommended_action"),
        "reason_for_escalation": tool_input.get("reason_for_escalation"),
    }

    order_in = tool_input.get("order")
    if isinstance(order_in, dict) and not _is_empty(order_in.get("id")):
        summary["order"] = {
            "id": order_in.get("id"),
            "status": order_in.get("status"),
            "amount": order_in.get("amount"),
        }

    return summary
