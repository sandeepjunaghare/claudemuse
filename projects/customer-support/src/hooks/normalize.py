"""Order-date normalization to canonical ISO 8601 (TR5).

`to_iso8601` is pure and SDK-free so it is exhaustively unit-testable; the
PostToolUse hook `normalize_order_dates` is a thin wrapper that rewrites the
`lookup_order` result before the model reasons over it.

WHY rewrite the TEXT (not a structured field): Task 0 established that the SDK
surfaces a tool's result to hooks AND to the model as ONLY its content list
(`[{"type":"text","text": ...}]`) — `structuredContent` is dropped entirely
(see `claude_agent_sdk/_internal/query.py:645-693`). So the text is the only
surface the model reasons over; normalizing it is both necessary and sufficient.
The raw heterogeneous date lives in `lookup_order`'s text as the trailing
`"... placed <value>."` segment (see `tools/server.py:134-137`); that "placed "
marker is the parsing contract between the tool and this hook.
"""

import re
from datetime import datetime, timezone

#: Canonical output format (UTC, trailing Z).
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

#: Human-string formats `lookup_order` may emit, tried in order.
_HUMAN_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d")

#: Captures the raw date in `"... placed <value>."` — the tool always renders the
#: order date as the final `placed <value>.` segment of the human text.
_PLACED_RE = re.compile(r"(placed\s+)(?P<raw>.+?)(\.?)$")


def to_iso8601(value) -> str:
    """Normalize a heterogeneous date value to canonical ISO 8601 (UTC).

    Accepts Unix timestamps (int/float or an all-digit string), ISO 8601
    (including a trailing ``Z``), and human strings like ``"Mar 5, 2025"``.
    Unparseable input is returned UNCHANGED — a hook must never raise and break
    the agent loop.
    """
    # Unix timestamp: int/float (but NOT bool — isinstance(True, int) is True).
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime(_ISO_FMT)

    if not isinstance(value, str):
        return value  # unknown type — leave it alone

    s = value.strip()
    if not s:
        return value

    # All-digit string -> treat as Unix timestamp.
    if s.isdigit():
        return datetime.fromtimestamp(int(s), tz=timezone.utc).strftime(_ISO_FMT)

    # ISO 8601. Python 3.10's fromisoformat does NOT accept a trailing "Z".
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime(_ISO_FMT)
    except ValueError:
        pass

    # Human strings.
    for fmt in _HUMAN_FORMATS:
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime(_ISO_FMT)
        except ValueError:
            continue

    return value  # unparseable — passthrough, never raise


def _normalize_text(text: str) -> str:
    """Rewrite the trailing `placed <raw>.` date segment to ISO 8601, if present."""
    m = _PLACED_RE.search(text)
    if not m:
        return text
    raw = m.group("raw").strip()
    iso = to_iso8601(raw if not raw.isdigit() else int(raw))
    if iso == raw:
        return text  # nothing changed (already ISO or unparseable)
    return text[: m.start("raw")] + iso + text[m.end("raw"):]


async def normalize_order_dates(input: dict, tool_use_id, context) -> dict:
    """PostToolUse hook: normalize the order date in `lookup_order` text (TR5).

    `tool_response` is the bare content list (Task 0). We rebuild it with the
    `placed <date>.` segment converted to ISO 8601 and return it via
    `updatedMCPToolOutput` — which must ALSO be the bare content list (Task 0:
    the `{"content": [...]}` wrapper makes the model see a tool failure).
    """
    # Defensive tool-name check — matcher semantics are not a correctness guarantee.
    if not input.get("tool_name", "").endswith("lookup_order"):
        return {}

    response = input.get("tool_response")
    if not isinstance(response, list):
        return {}

    new_items = []
    changed = False
    for item in response:
        if isinstance(item, dict) and item.get("type") == "text":
            new_text = _normalize_text(item.get("text", ""))
            if new_text != item.get("text"):
                changed = True
            new_items.append({**item, "text": new_text})
        else:
            new_items.append(item)

    if not changed:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedMCPToolOutput": new_items,  # bare list — see Task 0
        }
    }
