"""Deterministic proof of the TR9a RECORDER hook (no API).

The recorder is a PostToolUse writer that extracts facts from the tool content
text + `tool_input`. Tests feed it synthetic `tool_response` values in the
Task-0 bare-content-list shape and assert on the resulting store / rendered
block — never on prose. Error texts and multi/zero-match customer texts must
record nothing (preserving TR7); non-matching tools are a no-op; it never raises.
"""

from context import case_facts
from hooks.case_facts_recorder import case_facts_recorder


def _event(tool_name, text, tool_input=None):
    """A synthetic PostToolUse input in the Task-0 bare-content-list shape."""
    return {
        "tool_name": tool_name,
        "tool_response": [{"type": "text", "text": text}],
        "tool_input": tool_input or {},
        "session_id": "s",
    }


async def _run(tool_name, text, tool_input=None):
    return await case_facts_recorder(_event(tool_name, text, tool_input), None, {"signal": None})


async def test_records_customer_id_and_name():
    out = await _run("mcp__support__get_customer", "Verified customer Alice Wong (id C001).")
    assert out == {}  # never blocks/rewrites
    block = case_facts.render_block("s")
    assert "- customer_id: C001 (Alice Wong)" in block


async def test_records_order_facts_with_iso_normalization():
    # Unix-timestamp date in the text — the recorder normalizes it itself (TR5-independent).
    await _run(
        "mcp__support__lookup_order",
        "Order O1001: status shipped, total $42.00, placed 1740787200.",
        {"customer_id": "C001", "order_id": "O1001"},
    )
    block = case_facts.render_block("s")
    assert "O1001" in block
    assert "$42.00" in block
    assert "2025-03-01T00:00:00Z" in block  # 1740787200 -> ISO


async def test_records_order_facts_already_iso():
    await _run(
        "mcp__support__lookup_order",
        "Order O1003: status processing, total $120.00, placed 2025-03-15T14:30:00Z.",
    )
    block = case_facts.render_block("s")
    assert "O1003" in block and "$120.00" in block and "2025-03-15T14:30:00Z" in block


async def test_records_refund_amount_and_order():
    await _run(
        "mcp__support__process_refund",
        "Refund of $30.00 on order O1001 for customer C001 recorded.",
    )
    block = case_facts.render_block("s")
    assert "O1001" in block
    assert "$30.00" in block


async def test_multi_match_customer_records_nothing():
    """TR7 preserved: a multi-match text has no `(id C###)`, so nothing is recorded."""
    await _run(
        "mcp__support__get_customer",
        "Found 2 customers matching those details. Ask the customer for an additional identifier.",
    )
    assert case_facts.render_block("s") == ""


async def test_zero_match_customer_records_nothing():
    await _run("mcp__support__get_customer", "No customer found with those details.")
    assert case_facts.render_block("s") == ""


async def test_error_texts_record_nothing():
    """Error-as-text (the `[error: ...]` tag) never matches a success contract."""
    await _run(
        "mcp__support__lookup_order",
        "No order found with id 'O9'. [error: category=validation retryable=false]",
        {"customer_id": "C001", "order_id": "O9"},
    )
    await _run(
        "mcp__support__lookup_order",
        "The order service is temporarily unavailable (HTTP 503). [error: category=transient retryable=true]",
    )
    await _run(
        "mcp__support__process_refund",
        "Order O1004 is cancelled and cannot be refunded. [error: category=business retryable=false]",
    )
    assert case_facts.render_block("s") == ""


async def test_non_matching_tool_is_noop():
    out = await _run("mcp__support__escalate_to_human", "Escalated to a human support agent.")
    assert out == {}
    assert case_facts.render_block("s") == ""


async def test_malformed_response_does_not_raise():
    # A non-list tool_response (defensive): must be a silent no-op, never raise.
    out = await case_facts_recorder(
        {"tool_name": "mcp__support__lookup_order", "tool_response": None, "session_id": "s"},
        None,
        {"signal": None},
    )
    assert out == {}
    assert case_facts.render_block("s") == ""


async def test_full_case_accumulates_across_tools():
    await _run("mcp__support__get_customer", "Verified customer Alice Wong (id C001).")
    await _run(
        "mcp__support__lookup_order",
        "Order O1001: status shipped, total $42.00, placed 2025-03-01T00:00:00Z.",
        {"customer_id": "C001", "order_id": "O1001"},
    )
    await _run("mcp__support__process_refund", "Refund of $30.00 on order O1001 for customer C001 recorded.")
    block = case_facts.render_block("s")
    assert "C001" in block and "Alice Wong" in block
    assert "O1001" in block
    assert "$42.00" in block and "$30.00" in block
    assert "2025-03-01T00:00:00Z" in block
