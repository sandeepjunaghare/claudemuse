"""Deterministic proof of TR4 (no API): order/refund actions are impossible
before a single-match `get_customer`, multi-match never verifies, and verified
state is isolated per session.

Synthetic `tool_response` values use the EXACT Task-0 shape: a bare content list
`[{"type":"text","text": ...}]` (structuredContent is dropped before hooks see
it). The verified-customer store is reset before each test by the autouse
fixture in conftest.
"""

from hooks import verified_store
from hooks.prerequisite_gate import prerequisite_gate, record_verified_customer

# --- Task-0-shaped synthetic get_customer results --------------------------

_SINGLE_MATCH = [{"type": "text", "text": "Verified customer Alice Wong (id C001)."}]
_MULTI_MATCH = [{"type": "text", "text": (
    "Found 2 customers matching those details. Ask the customer for an additional "
    "identifier (email or phone) to confirm which account is theirs — do not guess."
)}]
_ZERO_MATCH = [{"type": "text", "text": (
    "No customer found with those details. Ask the customer to re-check their name, email, or phone."
)}]


def _customer_input(tool_response, session_id="s"):
    return {
        "tool_name": "mcp__support__get_customer",
        "tool_response": tool_response,
        "session_id": session_id,
    }


def _gate_input(customer_id, tool="lookup_order", session_id="s"):
    return {
        "tool_name": f"mcp__support__{tool}",
        "tool_input": {"customer_id": customer_id, "order_id": "O1001", "amount": 42},
        "session_id": session_id,
    }


def _decision(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


async def test_lookup_denied_before_verification():
    """TR4: lookup_order is blocked when the customer is not yet verified."""
    assert _decision(await prerequisite_gate(_gate_input("C001"), "tu", {"signal": None})) == "deny"


async def test_refund_denied_before_verification():
    """TR4: process_refund is provably impossible before verification."""
    inp = _gate_input("C001", tool="process_refund")
    assert _decision(await prerequisite_gate(inp, "tu", {"signal": None})) == "deny"


async def test_single_match_verifies_then_allows():
    """After a single-match get_customer, the same id is allowed for order/refund."""
    await record_verified_customer(_customer_input(_SINGLE_MATCH), "tu", {"signal": None})
    assert verified_store.is_verified("s", "C001")
    assert await prerequisite_gate(_gate_input("C001"), "tu", {"signal": None}) == {}
    assert await prerequisite_gate(_gate_input("C001", tool="process_refund"), "tu", {"signal": None}) == {}


async def test_verified_id_does_not_allow_a_different_id():
    """Verifying C001 must not unlock C002."""
    await record_verified_customer(_customer_input(_SINGLE_MATCH), "tu", {"signal": None})
    assert _decision(await prerequisite_gate(_gate_input("C002"), "tu", {"signal": None})) == "deny"


async def test_multi_match_never_verifies():
    """TR7 preserved: multiple matches do NOT verify; the gate stays closed."""
    await record_verified_customer(_customer_input(_MULTI_MATCH), "tu", {"signal": None})
    assert not verified_store.is_verified("s", "C003")
    assert not verified_store.is_verified("s", "C004")
    assert _decision(await prerequisite_gate(_gate_input("C003"), "tu", {"signal": None})) == "deny"


async def test_zero_match_never_verifies():
    """No customer found -> nothing verified -> subsequent lookup denied."""
    await record_verified_customer(_customer_input(_ZERO_MATCH), "tu", {"signal": None})
    assert _decision(await prerequisite_gate(_gate_input("C001"), "tu", {"signal": None})) == "deny"


async def test_session_isolation():
    """Verifying in session s1 must not allow the same id in session s2."""
    await record_verified_customer(_customer_input(_SINGLE_MATCH, session_id="s1"), "tu", {"signal": None})
    assert await prerequisite_gate(_gate_input("C001", session_id="s1"), "tu", {"signal": None}) == {}
    assert _decision(await prerequisite_gate(_gate_input("C001", session_id="s2"), "tu", {"signal": None})) == "deny"


async def test_missing_customer_id_is_denied():
    """A lookup with no customer_id at all is denied."""
    inp = {"tool_name": "mcp__support__lookup_order", "tool_input": {"order_id": "O1001"}, "session_id": "s"}
    assert _decision(await prerequisite_gate(inp, "tu", {"signal": None})) == "deny"


async def test_get_customer_itself_is_never_gated():
    """get_customer carries no customer_id prerequisite — it is never blocked."""
    inp = {"tool_name": "mcp__support__get_customer", "tool_input": {"name": "Alice Wong"}, "session_id": "s"}
    assert await prerequisite_gate(inp, "tu", {"signal": None}) == {}


async def test_deny_reason_mentions_get_customer():
    """The deny reason routes the model to verify first."""
    result = await prerequisite_gate(_gate_input("C001"), "tu", {"signal": None})
    assert "get_customer" in result["hookSpecificOutput"]["permissionDecisionReason"]
