"""In-memory mock backend: seeded customers + orders and pure accessors.

This module is intentionally SDK-free so the backend can be unit-tested in
isolation. Date formats on orders are deliberately heterogeneous — that is
staged setup for the Phase 2 PostToolUse normalization hook (TR5); do not
normalize here.
"""

import random
from typing import Optional

import config

# --- Seed data -------------------------------------------------------------

#: Customers keyed by customer_id. C003/C004 are a deliberate duplicate-name
#: pair ("John Smith") to force the multi-match → ask-for-identifier path (TR7).
CUSTOMERS: dict[str, dict] = {
    "C001": {"id": "C001", "name": "Alice Wong", "email": "alice@example.com", "phone": "555-0101"},
    "C002": {"id": "C002", "name": "Bob Martinez", "email": "bob@example.com", "phone": "555-0102"},
    "C003": {"id": "C003", "name": "John Smith", "email": "john.smith@example.com", "phone": "555-0103"},
    "C004": {"id": "C004", "name": "John Smith", "email": "jsmith2@example.com", "phone": "555-0104"},
}

#: Orders keyed by order_id. `placed_at` is intentionally heterogeneous:
#: Unix timestamp (int), human string, and ISO 8601 — normalized in Phase 2.
ORDERS: dict[str, dict] = {
    # Unix timestamp for 2025-03-01T00:00:00Z
    "O1001": {"id": "O1001", "customer_id": "C001", "status": "shipped", "total": 42.00, "placed_at": 1740787200},
    # Human string format; $900 total sets up the Phase 2 over-limit refund case
    "O1002": {"id": "O1002", "customer_id": "C002", "status": "delivered", "total": 900.00, "placed_at": "Mar 5, 2025"},
    # ISO 8601
    "O1003": {"id": "O1003", "customer_id": "C001", "status": "processing", "total": 120.00, "placed_at": "2025-03-15T14:30:00Z"},
    # Cancelled order — sets up the Phase 3 `business` error: a refund against a
    # cancelled order is a business-rule failure (the agent explains, never retries).
    "O1004": {"id": "O1004", "customer_id": "C001", "status": "cancelled", "total": 60.00, "placed_at": "2025-02-10T09:00:00Z"},
}

#: Phase 4 (TR9b): a deliberately VERBOSE raw order record — the shape a real
#: backend might hand back, with 40+ fields. `lookup_order` projects this down to
#: the ~5 that matter (the trim); the rest (warehouse_id, risk_score, ip_address,
#: internal_flags, ...) must NEVER reach the model. `status`/`total`/`placed_at`
#: are kept CONSISTENT with the slim `ORDERS` above, and `placed_at` stays
#: heterogeneous so TR5 date normalization is still exercised after the trim.
def _verbose(order_id: str, tracking_number: str, **extra) -> dict:
    """Build a 40+-field verbose record from the slim order + realistic noise."""
    slim = ORDERS[order_id]
    record = {
        # --- the ~5 fields the trim keeps ---
        "order_id": order_id,
        "customer_id": slim["customer_id"],
        "status": slim["status"],
        "total": slim["total"],
        "placed_at": slim["placed_at"],  # heterogeneous — normalized downstream (TR5)
        "tracking_number": tracking_number,
        # --- the verbose tail the trim must DROP ---
        "currency": "USD",
        "updated_at": "2025-03-20T11:00:00Z",
        "shipped_at": "2025-03-02T08:15:00Z",
        "delivered_at": None,
        "carrier": "UPS",
        "warehouse_id": "WH-07",
        "fulfillment_center": "FC-WEST-3",
        "line_items": [
            {"sku": "SKU-100", "qty": 1, "price": slim["total"]},
        ],
        "item_count": 1,
        "subtotal": round(slim["total"] * 0.9, 2),
        "tax": round(slim["total"] * 0.08, 2),
        "shipping_fee": 0.0,
        "discount_code": None,
        "gift_wrap": False,
        "customer_segment": "consumer",
        "loyalty_tier": "silver",
        "payment_method": "card",
        "payment_last4": "4242",
        "billing_zip": "94016",
        "shipping_address": "123 Market St, San Francisco, CA",
        "billing_address": "123 Market St, San Francisco, CA",
        "ip_address": "203.0.113.42",
        "user_agent": "Mozilla/5.0",
        "risk_score": 0.07,
        "internal_flags": ["none"],
        "notes": "auto-generated test record",
        "channel": "web",
        "locale": "en-US",
        "warehouse_region": "us-west",
        "promised_delivery": "2025-03-08T00:00:00Z",
        "weight_grams": 850,
        "package_count": 1,
        "signature_required": False,
        "insured": False,
        "return_window_days": 30,
        "refundable": slim["status"] != "cancelled",
        "source_system": "oms-v2",
    }
    record.update(extra)
    return record


#: Verbose records keyed by order_id (TR9b source for the `lookup_order` trim).
ORDER_DETAILS_VERBOSE: dict[str, dict] = {
    "O1001": _verbose("O1001", tracking_number="1Z999AA10123456784"),
    "O1002": _verbose("O1002", tracking_number="1Z999AA10123456785"),
    "O1003": _verbose("O1003", tracking_number="1Z999AA10123456786"),
    "O1004": _verbose("O1004", tracking_number="1Z999AA10123456787"),
}

#: Phase 3: the order backend is flaky — it returns a transient 503 ~10% of the
#: time (TR6), exercising category-driven retry. Live runs stay probabilistic;
#: unit tests force the failures deterministically via the seam below.
FLAKY_503_ENABLED = True

#: Test seam: a countdown of forced transient failures. While > 0, the next
#: `maybe_fail_transient()` call returns True and decrements it — letting unit
#: tests script an exact transient-then-success sequence with zero randomness.
#: Process-global like `verified_store`, so tests MUST reset it between cases
#: (autouse `reset_flaky` fixture in conftest).
_forced_failures = 0


def force_transient_failures(n: int) -> None:
    """Force the next `n` `maybe_fail_transient()` calls to report a 503 (test seam)."""
    global _forced_failures
    _forced_failures = n


def reset_flaky() -> None:
    """Clear any pending forced transient failures (call between tests)."""
    global _forced_failures
    _forced_failures = 0


# --- Accessors -------------------------------------------------------------


def find_customers(
    *,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> list[dict]:
    """Return all customers matching ANY provided identifier (case-insensitive).

    Returns 0, 1, or many records — the "John Smith" pair returns 2 for
    name="John Smith", which is what forces the ask-for-identifier path.
    """
    matches: list[dict] = []
    for cust in CUSTOMERS.values():
        if name is not None and cust["name"].lower() == name.strip().lower():
            matches.append(cust)
            continue
        if email is not None and cust["email"].lower() == email.strip().lower():
            matches.append(cust)
            continue
        if phone is not None and cust["phone"] == phone.strip():
            matches.append(cust)
            continue
    return matches


def get_order(order_id: str) -> Optional[dict]:
    """Return the slim order record for `order_id`, or None if unknown.

    Canonical record for existence/owner/status/total checks (used by
    `lookup_order`'s gate and by `process_refund`). The verbose record is only
    the projection source for the TR9b trim — see `get_order_verbose`.
    """
    return ORDERS.get(order_id)


def get_order_verbose(order_id: str) -> Optional[dict]:
    """Return the 40+-field verbose order record (TR9b trim source), or None."""
    return ORDER_DETAILS_VERBOSE.get(order_id)


def maybe_fail_transient() -> bool:
    """Whether the order backend should report a transient 503 on this call (TR6).

    The forced-failure seam is authoritative and checked FIRST so unit tests are
    fully deterministic; only when no forced failures remain does the probabilistic
    `FLAKY_503_ENABLED` path apply (live runs). `random.random()` is fine in app code.
    """
    global _forced_failures
    if _forced_failures > 0:
        _forced_failures -= 1
        return True
    return FLAKY_503_ENABLED and random.random() < config.FLAKY_503_PROBABILITY
