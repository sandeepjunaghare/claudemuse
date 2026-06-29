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
    """Return the order record for `order_id`, or None if unknown."""
    return ORDERS.get(order_id)


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
