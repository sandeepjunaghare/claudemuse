"""Per-session registry of verified customer ids (TR4 support).

Bridges two hooks: `record_verified_customer` (PostToolUse on `get_customer`)
writes here when a lookup resolves to exactly one customer; `prerequisite_gate`
(PreToolUse on `lookup_order`/`process_refund`) reads here to decide whether the
supplied `customer_id` may be acted on.

Keyed by `session_id` (from the SDK's BaseHookInput) so verified state never
leaks across concurrent runs or across tests — the store is process-global, so
tests MUST `reset()` between cases. SDK-free by design (mirrors `mocks.fixtures`)
so it unit-tests without the API.
"""

#: session_id -> set of verified customer ids. A missing/empty session_id is its
#: own bucket ("") rather than a crash.
_VERIFIED: dict[str, set[str]] = {}


def mark_verified(session_id: str, customer_id: str) -> None:
    """Record that `customer_id` was verified (single match) in this session."""
    _VERIFIED.setdefault(session_id or "", set()).add(customer_id)


def is_verified(session_id: str, customer_id: str) -> bool:
    """True iff `customer_id` was verified in this session."""
    return customer_id in _VERIFIED.get(session_id or "", set())


def reset(session_id: str | None = None) -> None:
    """Clear one session's verified set, or ALL sessions when `session_id` is None."""
    if session_id is None:
        _VERIFIED.clear()
    else:
        _VERIFIED.pop(session_id or "", None)
