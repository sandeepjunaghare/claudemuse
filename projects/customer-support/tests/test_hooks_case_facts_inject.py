"""Deterministic proof of the TR9a INJECT hook + the simulated-`/compact` guarantee.

The inject hook renders the session's case-facts block and returns it as
`additionalContext` (UserPromptSubmit allow-with-context). The headline proof:
because the block is re-supplied from the code-maintained store on EVERY prompt,
the exact figures are structurally independent of conversation history — so they
survive a `/compact` that summarizes/drops earlier turns. We assert that
property directly: the hook re-emits verbatim figures with NO history involved.
"""

from context import case_facts
from hooks.case_facts_inject import case_facts_inject


async def _run(session_id):
    return await case_facts_inject({"session_id": session_id, "prompt": "hi"}, None, {"signal": None})


async def test_empty_store_returns_empty_dict():
    """First prompt of any conversation (empty store) injects nothing -> no regression."""
    assert await _run("s") == {}


async def test_populated_store_injects_verbatim_context():
    case_facts.record_customer("s", "C001", "Alice Wong")
    case_facts.record_order("s", "O1001", status="shipped", total=42.0, placed_iso="2025-03-01T00:00:00Z")
    out = await _run("s")
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    ctx = hso["additionalContext"]
    assert "C001" in ctx and "Alice Wong" in ctx
    assert "O1001" in ctx and "$42.00" in ctx and "2025-03-01T00:00:00Z" in ctx


async def test_simulated_compact_facts_survive_history_independent():
    """Acceptance: exact $ amounts and order ids persist VERBATIM after a simulated
    `/compact`. The facts come from the store, not from conversation history, so
    even if all prior turns were summarized away, the inject hook re-supplies them.
    We model the worst case — zero history — by invoking the hook with only the
    session id and asserting the verbatim figures are still injected.
    """
    case_facts.record_customer("s", "C001", "Alice Wong")
    case_facts.record_order("s", "O1001", status="shipped", total=42.0, placed_iso="2025-03-01T00:00:00Z")
    case_facts.record_refund("s", "O1001", 30.0)

    # No `prompt` text, no transcript, no history — the only input is the session id,
    # exactly as it would be post-compaction. Verbatim figures must still appear.
    out = await case_facts_inject({"session_id": "s"}, None, {"signal": None})
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "O1001" in ctx          # order id survives verbatim
    assert "$42.00" in ctx         # order total survives verbatim
    assert "$30.00" in ctx         # refund amount survives verbatim
    assert "2025-03-01T00:00:00Z" in ctx  # ISO date survives verbatim


async def test_session_isolation():
    case_facts.record_customer("s1", "C001", "Alice Wong")
    assert await _run("s2") == {}  # a different session sees nothing
