"""Per-session transactional case-facts store (TR9a).

The deterministic half of context hygiene: as the agent works a case, a
PostToolUse recorder (`hooks.case_facts_recorder`) writes the exact figures it
sees in tool outputs — customer id/name, order ids, amounts, ISO dates — into
this store, and a UserPromptSubmit hook (`hooks.case_facts_inject`) renders them
into a block injected on EVERY prompt. Because the block is rebuilt from this
store each turn rather than recalled from conversation history, the figures are
structurally immune to history summarization (a `/compact`) — they cannot be
paraphrased away or dropped.

Mirrors `hooks.verified_store`: a process-global dict keyed by `session_id`,
SDK-free so it unit-tests without the API. The store is shared across the
process, so tests MUST `reset()` between cases.
"""

import config

#: session_id -> accumulated facts. Per-session value shape:
#:   {
#:     "customer_id": str | None,
#:     "customer_name": str | None,
#:     "orders": dict[str, dict],   # order_id -> {"status", "total", "placed_iso"}
#:     "refunds": list[dict],       # [{"order_id", "amount"}]
#:   }
#: A missing/empty session_id buckets under "" rather than crashing.
_FACTS: dict[str, dict] = {}


def _bucket(session_id: str) -> dict:
    """Return (creating if needed) the per-session facts bucket."""
    return _FACTS.setdefault(
        session_id or "",
        {"customer_id": None, "customer_name": None, "orders": {}, "refunds": []},
    )


def record_customer(session_id: str, customer_id: str, name: str | None = None) -> None:
    """Record the verified customer id (and name, if known) for the session."""
    if not customer_id:
        return
    facts = _bucket(session_id)
    facts["customer_id"] = customer_id
    if name:
        facts["customer_name"] = name


def record_order(
    session_id: str,
    order_id: str,
    status: str | None = None,
    total: float | None = None,
    placed_iso: str | None = None,
) -> None:
    """Merge facts for `order_id` into the session, never clobbering a known value.

    A later call that omits a field (passes ``None``) leaves any previously
    recorded value intact — so recording the id alone (e.g. from a refund) never
    erases the status/total learned earlier from a lookup.
    """
    if not order_id:
        return
    orders = _bucket(session_id)["orders"]
    order = orders.setdefault(order_id, {"status": None, "total": None, "placed_iso": None})
    if status is not None:
        order["status"] = status
    if total is not None:
        order["total"] = total
    if placed_iso is not None:
        order["placed_iso"] = placed_iso


def record_refund(session_id: str, order_id: str, amount: float) -> None:
    """Record a refund amount against an order (and ensure the order id is listed)."""
    if amount is None:
        return
    _bucket(session_id)["refunds"].append({"order_id": order_id, "amount": amount})
    # Ensure the order id appears in the rendered block even if never looked up.
    if order_id:
        record_order(session_id, order_id)


def _dedupe(values: list[str]) -> list[str]:
    """De-duplicate while preserving first-seen (insertion) order."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def render_block(session_id: str) -> str:
    """Render the PRD §10 case-facts block for the session, or ``""`` if none.

    The block is deterministic (stable ordering, ``$X.XX`` money formatting) so
    tests can assert exact substrings. Lines whose list is empty are omitted; an
    empty store renders ``""`` so first-turn / single-shot runs inject nothing.
    """
    facts = _FACTS.get(session_id or "")
    if not facts:
        return ""

    orders = facts["orders"]
    refunds = facts["refunds"]
    has_any = facts["customer_id"] or orders or refunds
    if not has_any:
        return ""

    lines = [config.CASE_FACTS_HEADER]

    if facts["customer_id"]:
        if facts["customer_name"]:
            lines.append(f"- customer_id: {facts['customer_id']} ({facts['customer_name']})")
        else:
            lines.append(f"- customer_id: {facts['customer_id']}")

    order_ids = list(orders.keys())
    if order_ids:
        lines.append(f"- order_id(s): {', '.join(order_ids)}")

    # Amounts = order totals (in order-insertion order) then refund amounts, de-duped.
    amounts = [f"${o['total']:.2f}" for o in orders.values() if o.get("total") is not None]
    amounts += [f"${r['amount']:.2f}" for r in refunds if r.get("amount") is not None]
    amounts = _dedupe(amounts)
    if amounts:
        lines.append(f"- amounts: {', '.join(amounts)}")

    dates = _dedupe([o["placed_iso"] for o in orders.values() if o.get("placed_iso")])
    if dates:
        lines.append(f"- dates (ISO 8601): {', '.join(dates)}")

    return "\n".join(lines)


def reset(session_id: str | None = None) -> None:
    """Clear one session's facts, or ALL sessions when `session_id` is None."""
    if session_id is None:
        _FACTS.clear()
    else:
        _FACTS.pop(session_id or "", None)
