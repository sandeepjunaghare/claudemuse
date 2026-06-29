"""Deterministic proof of the TR9a case-facts STORE + render (no API).

Asserts the store accumulates the exact transactional figures across tools, that
`render_block` emits the PRD §10 block with verbatim figures and stable ordering,
that an empty store renders ``""``, and that sessions are isolated and resettable.
The autouse `_reset_case_facts` fixture (conftest) clears the store per test.
"""

import config
from context import case_facts


def test_render_block_accumulates_verbatim_figures():
    case_facts.record_customer("s", "C001", "Alice Wong")
    case_facts.record_order("s", "O1001", status="shipped", total=42.0, placed_iso="2025-03-01T00:00:00Z")
    case_facts.record_order("s", "O1003", status="processing", total=120.0, placed_iso="2025-03-15T14:30:00Z")
    case_facts.record_refund("s", "O1001", 30.0)

    block = case_facts.render_block("s")
    assert block.startswith(config.CASE_FACTS_HEADER)
    # Customer id + name verbatim.
    assert "- customer_id: C001 (Alice Wong)" in block
    # Both order ids listed, in insertion order.
    assert "- order_id(s): O1001, O1003" in block
    # Amounts: order totals then refund, verbatim $X.XX.
    assert "$42.00" in block and "$120.00" in block and "$30.00" in block
    # ISO dates listed.
    assert "2025-03-01T00:00:00Z" in block and "2025-03-15T14:30:00Z" in block


def test_record_order_never_clobbers_known_value_with_none():
    case_facts.record_order("s", "O1001", status="shipped", total=42.0, placed_iso="2025-03-01T00:00:00Z")
    # A later id-only record (e.g. from a refund) must not erase the known fields.
    case_facts.record_order("s", "O1001")
    block = case_facts.render_block("s")
    assert "$42.00" in block
    assert "2025-03-01T00:00:00Z" in block


def test_amounts_deduped_in_insertion_order():
    # Two orders share the same total + a refund of that total — de-duped to one entry.
    case_facts.record_order("s", "O1001", total=42.0)
    case_facts.record_order("s", "O1002", total=42.0)
    case_facts.record_refund("s", "O1001", 42.0)
    block = case_facts.render_block("s")
    amounts_line = [ln for ln in block.splitlines() if ln.startswith("- amounts:")][0]
    assert amounts_line == "- amounts: $42.00"


def test_empty_store_renders_empty_string():
    assert case_facts.render_block("s") == ""
    # A bucket touched but with no facts still renders empty.
    assert case_facts.render_block("never-seen") == ""


def test_lines_omitted_when_list_empty():
    # Only a customer recorded — no order/amount/date lines.
    case_facts.record_customer("s", "C002", "Bob Martinez")
    block = case_facts.render_block("s")
    assert "- customer_id: C002 (Bob Martinez)" in block
    assert "order_id(s)" not in block
    assert "amounts" not in block
    assert "dates" not in block


def test_session_isolation_and_reset():
    case_facts.record_customer("s1", "C001", "Alice Wong")
    case_facts.record_customer("s2", "C002", "Bob Martinez")
    assert "C001" in case_facts.render_block("s1")
    assert "C002" in case_facts.render_block("s2")
    # Reset one session leaves the other intact.
    case_facts.reset("s1")
    assert case_facts.render_block("s1") == ""
    assert "C002" in case_facts.render_block("s2")
    # Reset all clears everything.
    case_facts.reset()
    assert case_facts.render_block("s2") == ""


def test_customer_without_name():
    case_facts.record_customer("s", "C001")
    block = case_facts.render_block("s")
    assert "- customer_id: C001" in block
    assert "(" not in block.splitlines()[1]  # no name parens
