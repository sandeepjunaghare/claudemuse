"""The four MCP tools (TR2), backed by the in-memory mock.

Rich, disambiguating descriptions are the deliverable here. `get_customer` and
`lookup_order` are deliberately similar; they must be separable **by description
alone** (the system prompt is not allowed to do the disambiguating). Each
description states purpose, input formats, example values, edge cases, and
explicit "use this vs the other tool" guidance.

Phase 1 scope: tools return the standard content shape with `is_error=False`.
Structured error categories (TR6), the refund PreToolUse gate (TR3), the
prerequisite gate (TR4), and date normalization (TR5) all attach in later
phases without re-shaping these tools.
"""

import json
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

import config
import errors
import handoff
from mocks import fixtures


def _text(text: str) -> dict[str, Any]:
    """Wrap a human-readable string in the MCP content envelope."""
    return {"type": "text", "text": text}


def _result(text: str, structured: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
    """Standard tool return shape: human-readable content + machine-readable struct."""
    return {
        "content": [_text(text)],
        "structuredContent": structured,
        "is_error": is_error,
    }


@tool(
    "get_customer",
    (
        "Identify and VERIFY a CUSTOMER (a person/account) from their personal "
        "identifiers. Use this FIRST to establish who you are talking to, before any "
        "order lookup, account change, or financial operation — it returns the verified "
        "customer_id that those later steps require.\n\n"
        "Inputs (provide at least one): `name` (full name, e.g. \"Alice Wong\"), "
        "`email` (e.g. \"alice@example.com\"), or `phone` (e.g. \"555-0101\").\n\n"
        "Returns: 0 matches (no such customer — ask the user to re-check their details), "
        "exactly 1 match (verified — proceed), or MULTIPLE matches (e.g. two people named "
        "\"John Smith\"). On multiple matches, ASK the user for an additional identifier "
        "(email or phone) to disambiguate — never guess which one they are.\n\n"
        "Do NOT use this to fetch order status, tracking, or order contents — that is what "
        "`lookup_order` is for. This tool finds the PERSON; `lookup_order` finds their ORDER."
    ),
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Customer full name, e.g. 'Alice Wong'."},
            "email": {"type": "string", "description": "Customer email, e.g. 'alice@example.com'."},
            "phone": {"type": "string", "description": "Customer phone, e.g. '555-0101'."},
        },
        "required": [],
    },
)
async def get_customer(args: dict[str, Any]) -> dict[str, Any]:
    """Look up customers by name/email/phone; report 0/1/many matches."""
    name = args.get("name")
    email = args.get("email")
    phone = args.get("phone")

    if not any([name, email, phone]):
        # No input to search on — a validation error (the agent should ask the
        # customer for an identifier, not retry). 0/1/many MATCHES below stay
        # non-error: multi-match is the TR7 ask-for-identifier path, not a failure.
        return errors.validation_error(
            "No identifier provided. Ask the customer for a name, email, or phone number."
        )

    matches = fixtures.find_customers(name=name, email=email, phone=phone)
    slim = [{"id": c["id"], "name": c["name"], "email": c["email"]} for c in matches]

    if len(matches) == 0:
        text = "No customer found with those details. Ask the customer to re-check their name, email, or phone."
    elif len(matches) == 1:
        text = f"Verified customer {matches[0]['name']} (id {matches[0]['id']})."
    else:
        text = (
            f"Found {len(matches)} customers matching those details. Ask the customer for an "
            "additional identifier (email or phone) to confirm which account is theirs — do not guess."
        )

    return _result(text, {"matchCount": len(matches), "matches": slim})


@tool(
    "lookup_order",
    (
        "Fetch the details/status of a specific ORDER that belongs to an already-VERIFIED "
        "customer. Use this to answer order-status, shipping/tracking, or order-contents "
        "questions.\n\n"
        "Inputs (both required): `customer_id` — the verified id returned by `get_customer` "
        "(e.g. \"C001\"); `order_id` — the order to fetch (e.g. \"O1001\").\n\n"
        "Returns: the order's status (e.g. shipped/delivered/processing), total amount, and "
        "the date it was placed.\n\n"
        "Prerequisite: you must have a verified `customer_id` from `get_customer` first — do "
        "NOT call this to identify or verify a person. If you only know the customer's name or "
        "email, call `get_customer` first. This tool finds the ORDER; `get_customer` finds the "
        "PERSON."
    ),
    {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "Verified customer id from get_customer, e.g. 'C001'."},
            "order_id": {"type": "string", "description": "Order id to fetch, e.g. 'O1001'."},
        },
        "required": ["customer_id", "order_id"],
    },
)
async def lookup_order(args: dict[str, Any]) -> dict[str, Any]:
    """Fetch a single order for a verified customer."""
    customer_id = args.get("customer_id")
    order_id = args.get("order_id")

    # Transient check FIRST: a flaky-backend 503 must be reported as retryable,
    # never misclassified as a (non-retryable) unknown-order/owner-mismatch error.
    if fixtures.maybe_fail_transient():
        return errors.transient_error(
            "The order service is temporarily unavailable (HTTP 503). "
            "This is a transient error; retry the request."
        )

    order = fixtures.get_order(order_id) if order_id else None

    if order is None:
        return errors.validation_error(
            f"No order found with id {order_id!r}. Ask the customer to confirm their order number."
        )

    if order["customer_id"] != customer_id:
        return errors.permission_error(
            f"Order {order_id} is not associated with customer {customer_id}."
        )

    text = (
        f"Order {order['id']}: status {order['status']}, total ${order['total']:.2f}, "
        f"placed {order['placed_at']}."
    )
    structured = {
        "found": True,
        "orderId": order["id"],
        "status": order["status"],
        "total": order["total"],
        "placedAt": order["placed_at"],  # heterogeneous format; normalized in Phase 2 (TR5)
    }
    return _result(text, structured)


@tool(
    "process_refund",
    (
        "Issue a refund for an order belonging to a VERIFIED customer, WITHIN policy. Use "
        "this to refund a customer for a returned, damaged, or incorrectly-charged order when "
        "the amount is within the standard policy limit.\n\n"
        "Inputs: `customer_id` (verified, from `get_customer`), `order_id`, `amount` (USD, "
        "e.g. 42.00), and optionally `reason` (e.g. 'item arrived damaged').\n\n"
        "Large or out-of-policy refunds are NOT handled here — they are routed to a human "
        "instead (use `escalate_to_human`). Requires a verified customer; never refund against "
        "an unidentified person."
    ),
    {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "Verified customer id, e.g. 'C001'."},
            "order_id": {"type": "string", "description": "Order id to refund, e.g. 'O1001'."},
            "amount": {"type": "number", "description": "Refund amount in USD, e.g. 42.00."},
            "reason": {"type": "string", "description": "Optional reason, e.g. 'item arrived damaged'."},
        },
        "required": ["customer_id", "order_id", "amount"],
    },
)
async def process_refund(args: dict[str, Any]) -> dict[str, Any]:
    """Issue an in-policy refund, or return a `business` error if the order can't be refunded.

    The over-limit ceiling (TR3) is enforced by the `refund_gate` PreToolUse hook
    BEFORE this runs — do not duplicate it here. This tool's own failure mode is a
    business-rule one (non-refundable order / amount over the order total): the
    agent should explain it to the customer, not retry blindly.
    """
    customer_id = args.get("customer_id")
    order_id = args.get("order_id")
    amount = args.get("amount")

    order = fixtures.get_order(order_id) if order_id else None
    if order is not None:
        if order["status"] == "cancelled":
            return errors.business_error(
                f"Order {order_id} is cancelled and cannot be refunded. Explain this to the "
                "customer; if they dispute it, escalate to a human."
            )
        try:
            amount_val = float(amount)
        except (TypeError, ValueError):
            amount_val = 0.0
        if amount_val > order["total"]:
            return errors.business_error(
                f"Refund amount ${amount_val:.2f} exceeds the order total ${order['total']:.2f} "
                f"for order {order_id}. Refund at most the order total."
            )

    text = f"Refund of ${float(amount):.2f} on order {order_id} for customer {customer_id} recorded."
    return _result(
        text,
        {"refunded": True, "orderId": order_id, "amount": amount, "customerId": customer_id},
    )


@tool(
    "escalate_to_human",
    (
        "Hand the case off to a human support agent with a SELF-CONTAINED summary. Use this "
        "when the customer explicitly asks for a human/manager, when policy is silent or "
        "ambiguous, when a refund or action exceeds policy, or when you cannot make progress.\n\n"
        "The human CANNOT see this conversation — they only see the fields you provide here, so "
        "fill them in completely from what you learned. Required:\n"
        "- `reason_for_escalation`: one of 'explicit_request' (customer asked for a human), "
        "'policy_gap' (policy is silent/ambiguous), 'over_limit_refund' (refund exceeded the "
        "policy limit), or 'stalled' (you cannot make progress).\n"
        "- `root_cause`: the underlying problem in one or two sentences.\n"
        "- `recommended_action`: what you suggest the human do next.\n"
        "- `actions_taken`: a list of what you already did this contact (may be empty for an "
        "immediate escalation).\n"
        "- `customer`: an object `{id, name, verified}` — at minimum the verified customer id.\n"
        "Optional: `order` (object `{id, status, amount}`) when an order is involved, and a free-text "
        "`reason` for extra readability.\n\n"
        "If you call this with fields missing, the handoff will be rejected and you will be asked "
        "to provide them — supply everything the first time."
    ),
    {
        "type": "object",
        "properties": {
            "reason_for_escalation": {
                "type": "string",
                "enum": list(handoff.REASON_VALUES),
                "description": "Why this needs a human: explicit_request | policy_gap | over_limit_refund | stalled.",
            },
            "root_cause": {"type": "string", "description": "The underlying problem, 1-2 sentences."},
            "recommended_action": {"type": "string", "description": "What the human should do next."},
            "actions_taken": {
                "type": "array",
                "items": {"type": "string"},
                "description": "What you already did this contact (may be an empty list).",
            },
            "customer": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Verified customer id, e.g. 'C001'."},
                    "name": {"type": "string", "description": "Customer name, e.g. 'Alice Wong'."},
                    "verified": {"type": "boolean", "description": "Whether identity was verified."},
                },
                "description": "Customer context; at minimum the verified id.",
            },
            "order": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Order id, e.g. 'O1001'."},
                    "status": {"type": "string", "description": "Order status, e.g. 'shipped'."},
                    "amount": {"type": "number", "description": "Order/refund amount in USD."},
                },
                "description": "Optional order context when an order is involved.",
            },
            "reason": {"type": "string", "description": "Optional free-text summary for readability."},
        },
        "required": ["reason_for_escalation", "root_cause", "recommended_action", "actions_taken"],
    },
)
async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
    """Emit a self-contained handoff JSON for a human (TR8).

    Completeness is guaranteed UPSTREAM by the `handoff_gate` PreToolUse hook, so
    by the time this runs the required fields are present and the enum is valid.
    `build_summary` assembles the PRD §10 shape defensively (omits an absent
    optional order, never raises); the JSON is serialized into the content text so
    it is inspectable end-to-end (the model-visible surface — Phase 2 Task-0).
    """
    summary = handoff.build_summary(args)
    text = (
        "Escalated to a human support agent. Handoff summary (the human will act on this):\n"
        + json.dumps(summary)
    )
    return _result(text, {"escalated": True, "handoff": summary})


#: In-process MCP server exposing exactly the four tools (TR2 / least privilege).
support_server = create_sdk_mcp_server(
    name=config.MCP_SERVER_NAME,
    version="1.0.0",
    tools=[get_customer, lookup_order, process_refund, escalate_to_human],
)
