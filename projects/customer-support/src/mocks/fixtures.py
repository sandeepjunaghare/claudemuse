"""In-memory mock backend: seeded customers + orders and pure accessors.

This module is intentionally SDK-free so the backend can be unit-tested in
isolation. Date formats on orders are deliberately heterogeneous — that is
staged setup for the Phase 2 PostToolUse normalization hook (TR5); do not
normalize here.
"""

from typing import Optional

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
}

#: Phase 3 will flip this on to exercise transient (503) retry handling (TR6).
#: Inert in Phase 1 so the suite stays deterministic.
FLAKY_503_ENABLED = False


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
    """Return the order record for `order_id`, or None if unknown."""
    return ORDERS.get(order_id)


def maybe_fail_transient() -> None:
    """No-op stub for Phase 1. Phase 3 will raise/return a transient 503 here
    when `FLAKY_503_ENABLED` is true, to exercise category-driven retry (TR6)."""
    return None
