"""Order lookup helpers.

SEEDED FIXTURE INTENT: this file carries ONE unambiguous, GENERAL bug — a
None-deref on a realistic lookup-miss path (``db.get`` returns ``None`` when the
id is absent, then ``.name`` raises ``AttributeError``). It needs no project
convention to recognize, so BOTH the baseline and enriched prompts should flag
it — it keeps recall high while precision is what the fixture moves.
Ground-truth case: ``none-deref`` (should_flag=true, high, correctness).
"""


def find_order(order_id, db):
    """Return the order record for ``order_id`` from ``db`` (a dict-like)."""
    return db.get(order_id)


def order_summary(order_id, db):
    """Build a one-line summary for an order.

    BUG: ``find_order`` returns ``None`` on a lookup miss, so ``order.total``
    dereferences ``None`` and raises ``AttributeError`` on any unknown id.
    """
    order = find_order(order_id, db)
    return f"Order {order_id}: ${order.total:.2f} for {order.customer}"
