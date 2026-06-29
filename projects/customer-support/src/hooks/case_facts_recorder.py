"""Case-facts recorder (TR9a): a PostToolUse writer that extracts the exact
transactional figures from tool outputs and writes them to `context.case_facts`.

This is the deterministic, code-driven half of TR9a — the figures come from the
tool **content text** + the **`tool_input`**, parsed by code, so the model can
never paraphrase, round, or drop them. It mirrors
`prerequisite_gate.record_verified_customer`: a defensive tool-name guard, the
shared `_extract_text` bare-content-list joiner, a store write, and an
unconditional `return {}` (it never blocks or rewrites a result).

Parsing notes (the Phase 2/3 finding, do NOT re-guess):
- `tool_response` is the BARE content list `[{"type":"text","text": ...}]`;
  `structuredContent` is dropped by the SDK before any hook sees it. So every
  fact is recovered from the text + `tool_input`.
- The date is normalized with `to_iso8601` HERE, so recording is independent of
  whether `normalize_order_dates` (the TR5 hook on the same matcher) ran first —
  PostToolUse hook ordering on a shared matcher is not a guarantee to lean on.
- The whole body is wrapped defensively: a parse miss is a no-op, never an
  exception. A PostToolUse hook that raises would break the agent loop.
"""

import re

from context import case_facts
from hooks.normalize import to_iso8601
from hooks.prerequisite_gate import _extract_text

#: Single-match `get_customer` sentence (tools/server.py:86), extended to also
#: capture the name. Multi/zero-match texts lack `(id C###)`, so they never match
#: — preserving the TR7 ask-for-identifier path (nothing is recorded for them).
_CUSTOMER_RE = re.compile(r"Verified customer (?P<name>.+?) \(id\s+(?P<id>[A-Za-z0-9]+)\)")

#: `lookup_order` success contract (tools/server.py:145-148). The date is the
#: final `placed <date>.` segment, matching the TR5 `normalize._PLACED_RE` shape.
_ORDER_RE = re.compile(
    r"Order (?P<oid>\S+): status (?P<status>\w+), total \$(?P<total>[\d.]+), placed (?P<date>.+?)\.?$"
)

#: `process_refund` success contract (tools/server.py:211).
_REFUND_RE = re.compile(r"Refund of \$(?P<amt>[\d.]+) on order (?P<oid>\S+)")


async def case_facts_recorder(input: dict, tool_use_id, context) -> dict:
    """PostToolUse writer: record customer/order/refund facts from tool output (TR9a).

    Never blocks or rewrites — always returns ``{}``. Errors-as-text (the
    `[error: ...]` tag) and multi/zero-match customer texts don't match the
    success contracts, so nothing is recorded for them.
    """
    tool_name = input.get("tool_name", "")
    session_id = input.get("session_id", "")
    text = _extract_text(input.get("tool_response"))
    tool_input = input.get("tool_input") or {}

    try:
        if tool_name.endswith("get_customer"):
            m = _CUSTOMER_RE.search(text)
            if m:
                case_facts.record_customer(session_id, m.group("id"), m.group("name"))

        elif tool_name.endswith("lookup_order"):
            m = _ORDER_RE.search(text)
            if m:
                case_facts.record_order(
                    session_id,
                    m.group("oid"),
                    status=m.group("status"),
                    total=float(m.group("total")),
                    placed_iso=to_iso8601(m.group("date").strip()),
                )

        elif tool_name.endswith("process_refund"):
            m = _REFUND_RE.search(text)
            if m:
                case_facts.record_refund(session_id, m.group("oid"), float(m.group("amt")))
    except Exception:
        # A PostToolUse hook must never raise — a parse miss is simply a no-op.
        pass

    return {}
