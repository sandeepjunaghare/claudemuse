"""Deterministic proof of TR5 (no API): heterogeneous order dates normalize to
canonical ISO 8601, and the PostToolUse hook rewrites the date in the text the
model actually reads.

The hook operates on the Task-0 tool_response shape: a bare content list
`[{"type":"text","text": ...}]`. (structuredContent never reaches the model, so
the text is the sole surface to normalize.)
"""

import pytest

from hooks.normalize import normalize_order_dates, to_iso8601
from mocks import fixtures


@pytest.mark.parametrize(
    "value, expected",
    [
        (1740787200, "2025-03-01T00:00:00Z"),     # Unix int (O1001)
        ("1740787200", "2025-03-01T00:00:00Z"),   # all-digit string
        ("Mar 5, 2025", "2025-03-05T00:00:00Z"),  # human string (O1002)
        ("2025-03-15T14:30:00Z", "2025-03-15T14:30:00Z"),  # ISO with Z (O1003)
        ("2025-03-15", "2025-03-15T00:00:00Z"),   # bare ISO date
        ("not a date", "not a date"),             # unparseable -> passthrough
        ("", ""),                                 # empty -> passthrough
        (True, True),                             # bool guard -> passthrough (not a timestamp)
        (None, None),                             # unknown type -> passthrough
    ],
)
def test_to_iso8601(value, expected):
    assert to_iso8601(value) == expected


def test_all_three_fixture_formats_normalize():
    """Every heterogeneous fixture date maps to canonical ISO 8601."""
    assert to_iso8601(fixtures.ORDERS["O1001"]["placed_at"]) == "2025-03-01T00:00:00Z"
    assert to_iso8601(fixtures.ORDERS["O1002"]["placed_at"]) == "2025-03-05T00:00:00Z"
    assert to_iso8601(fixtures.ORDERS["O1003"]["placed_at"]) == "2025-03-15T14:30:00Z"


def _lookup_response(text):
    """A synthetic lookup_order tool_response in the Task-0 bare-list shape."""
    return {
        "tool_name": "mcp__support__lookup_order",
        "tool_response": [{"type": "text", "text": text}],
        "session_id": "s",
    }


async def test_hook_rewrites_unix_date_in_text():
    """The Unix-timestamp date is replaced by ISO in the content the model sees."""
    raw = "Order O1001: status shipped, total $42.00, placed 1740787200."
    out = await normalize_order_dates(_lookup_response(raw), "tu", {"signal": None})
    new = out["hookSpecificOutput"]["updatedMCPToolOutput"]
    # updatedMCPToolOutput is the BARE list (Task 0), not a {"content": ...} wrapper.
    assert isinstance(new, list)
    text = new[0]["text"]
    assert "2025-03-01T00:00:00Z" in text
    assert "1740787200" not in text


async def test_hook_rewrites_human_date_in_text():
    raw = "Order O1002: status delivered, total $900.00, placed Mar 5, 2025."
    out = await normalize_order_dates(_lookup_response(raw), "tu", {"signal": None})
    text = out["hookSpecificOutput"]["updatedMCPToolOutput"][0]["text"]
    assert "2025-03-05T00:00:00Z" in text
    assert "Mar 5, 2025" not in text


async def test_hook_noop_when_already_iso():
    """An ISO date is unchanged -> hook returns {} (no rewrite needed)."""
    raw = "Order O1003: status processing, total $120.00, placed 2025-03-15T14:30:00Z."
    out = await normalize_order_dates(_lookup_response(raw), "tu", {"signal": None})
    assert out == {}


async def test_hook_ignores_non_lookup_tool():
    inp = {"tool_name": "mcp__support__get_customer",
           "tool_response": [{"type": "text", "text": "Verified customer (id C001)."}]}
    assert await normalize_order_dates(inp, "tu", {"signal": None}) == {}


async def test_hook_tolerates_non_list_response():
    """A malformed (non-list) tool_response must not raise — just pass through."""
    inp = {"tool_name": "mcp__support__lookup_order", "tool_response": None}
    assert await normalize_order_dates(inp, "tu", {"signal": None}) == {}
