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

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

import config
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
        return _result(
            "No identifier provided. Ask the customer for a name, email, or phone number.",
            {"matchCount": 0, "matches": []},
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

    order = fixtures.get_order(order_id) if order_id else None

    if order is None:
        return _result(
            f"No order found with id {order_id!r}. Ask the customer to confirm their order number.",
            {"found": False, "orderId": order_id},
        )

    if order["customer_id"] != customer_id:
        return _result(
            f"Order {order_id} is not associated with customer {customer_id}.",
            {"found": False, "orderId": order_id, "ownerMismatch": True},
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
    """Phase 1 stub: confirm a refund. Deterministic limit enforcement is Phase 2 (TR3)."""
    customer_id = args.get("customer_id")
    order_id = args.get("order_id")
    amount = args.get("amount")
    text = f"Refund of ${float(amount):.2f} on order {order_id} for customer {customer_id} recorded."
    return _result(
        text,
        {"refunded": True, "orderId": order_id, "amount": amount, "customerId": customer_id},
    )


@tool(
    "escalate_to_human",
    (
        "Hand the case off to a human support agent. Use this when the customer explicitly "
        "asks for a human/manager, when policy is silent or ambiguous, when a refund or action "
        "exceeds policy, or when you cannot make progress.\n\n"
        "Inputs: `reason` (why this needs a human), and optionally `customer_id` and `order_id` "
        "for context.\n\n"
        "The human cannot see this conversation, so the escalation should carry enough context "
        "to act on. (The full self-contained handoff summary is added in a later phase — TR8.)"
    ),
    {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why this case needs a human."},
            "customer_id": {"type": "string", "description": "Optional verified customer id for context."},
            "order_id": {"type": "string", "description": "Optional order id for context."},
        },
        "required": ["reason"],
    },
)
async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
    """Phase 1 stub: acknowledge an escalation. Full handoff JSON is Phase 3 (TR8)."""
    reason = args.get("reason", "")
    return _result(
        "Escalated to a human support agent. The customer will be contacted shortly.",
        {"escalated": True, "reason": reason,
         "customerId": args.get("customer_id"), "orderId": args.get("order_id")},
    )


#: In-process MCP server exposing exactly the four tools (TR2 / least privilege).
support_server = create_sdk_mcp_server(
    name=config.MCP_SERVER_NAME,
    version="1.0.0",
    tools=[get_customer, lookup_order, process_refund, escalate_to_human],
)
