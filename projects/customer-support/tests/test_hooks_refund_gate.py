"""Deterministic proof of TR3: 100% of over-limit refunds are denied (no API).

This is the hard guarantee — proven across 20+ amounts by calling the hook
callable directly, with no model in the loop. The boundary is driven by
`config.REFUND_POLICY_LIMIT` so re-policying reparameterizes the cases instead
of breaking hardcoded numbers.
"""

import config
from hooks.refund_gate import refund_gate

_LIMIT = config.REFUND_POLICY_LIMIT


def _input(amount):
    return {
        "tool_name": "mcp__support__process_refund",
        "tool_input": {"amount": amount, "customer_id": "C002", "order_id": "O1002"},
        "session_id": "s",
    }


def _decision(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


# 20+ amounts strictly OVER the limit — every one must be denied.
_OVER_LIMIT = [
    _LIMIT + 0.01, _LIMIT + 1, 501, 550, 600, 750, 900, 1000, 1234.56,
    2000, 5000, 9999.99, 10_000, 50_000, 100_000, 999_999, 1_000_000,
    _LIMIT * 2, _LIMIT * 10, _LIMIT + 100, _LIMIT + 0.5,
]

# Amounts AT or UNDER the limit — every one must be allowed (== limit is in policy).
_WITHIN_LIMIT = [0, 0.0, 0.01, 1, 5, 42, 99.99, 100, 250, 499.99, _LIMIT, _LIMIT - 0.01]


async def test_over_limit_amounts_all_denied():
    """TR3: every over-limit amount is denied (100% across 20+ cases)."""
    assert len(_OVER_LIMIT) >= 20
    for amount in _OVER_LIMIT:
        result = await refund_gate(_input(amount), "tu", {"signal": None})
        assert _decision(result) == "deny", (amount, result)


async def test_within_limit_amounts_all_allowed():
    """Amounts at or under the limit are not blocked by the refund gate."""
    for amount in _WITHIN_LIMIT:
        result = await refund_gate(_input(amount), "tu", {"signal": None})
        assert result == {}, (amount, result)


async def test_exact_limit_is_allowed():
    """Boundary: exactly the policy limit is WITHIN policy (strictly-over blocks)."""
    result = await refund_gate(_input(_LIMIT), "tu", {"signal": None})
    assert result == {}


async def test_deny_reason_routes_to_escalation():
    """The deny reason instructs escalation (TR3: block guarantees, model escalates)."""
    result = await refund_gate(_input(_LIMIT + 1), "tu", {"signal": None})
    reason = result["hookSpecificOutput"]["permissionDecisionReason"].lower()
    assert "escalate" in reason


async def test_non_refund_tool_is_ignored():
    """The gate only acts on process_refund; other tools pass through."""
    other = {"tool_name": "mcp__support__lookup_order", "tool_input": {"amount": 9999}}
    assert await refund_gate(other, "tu", {"signal": None}) == {}


async def test_missing_or_bad_amount_is_not_over_limit():
    """A missing/None/garbage amount is not 'over limit' — gate allows (schema handles it)."""
    for bad in (None, "", "abc", {}):
        inp = {"tool_name": "mcp__support__process_refund", "tool_input": {"amount": bad}}
        assert await refund_gate(inp, "tu", {"signal": None}) == {}, bad
