"""Structured tool-error envelope (TR6).

Tools that fail return one of these envelopes. The model's ONLY structured signal
is the **content text** plus the bare `is_error` flag: the Phase 2 Task-0 finding
(re-confirmed in SDK source at `claude_agent_sdk/_internal/query.py:644-695`) proved
`structuredContent` is dropped before the model or any hook sees it. So the
error *category* and *retryability* are serialized into the text as a terse,
consistent tag — `[error: category=<cat> retryable=<bool>]` — that the system
prompt's few-shots reference verbatim, and the message itself is phrased as an
actionable next step (retry / explain / ask).

`structuredContent` is still populated for contract fidelity (PRD §10) and
future-proofing, but it is inert at runtime — the text is the operative surface.

Pure and SDK-free (mirrors `mocks.fixtures`) so it is exhaustively unit-testable.
Retryability semantics for this build: only `transient` is retryable;
`validation`, `business`, and `permission` are not.
"""

from typing import Any

# --- Category constants ----------------------------------------------------

TRANSIENT = "transient"
VALIDATION = "validation"
BUSINESS = "business"
PERMISSION = "permission"


def error_result(message: str, category: str, is_retryable: bool) -> dict[str, Any]:
    """Build the standard tool error dict for `message`/`category`/`is_retryable`.

    The category + retryability are embedded in the content text (the only
    model-visible structured surface); `structuredContent` mirrors the PRD §10
    envelope; `is_error=True` surfaces as MCP `isError`.
    """
    tag = f"[error: category={category} retryable={'true' if is_retryable else 'false'}]"
    return {
        "content": [{"type": "text", "text": f"{message} {tag}"}],
        "structuredContent": {
            "isError": True,
            "errorCategory": category,
            "isRetryable": is_retryable,
            "message": message,
        },
        "is_error": True,
    }


def transient_error(message: str) -> dict[str, Any]:
    """A retryable transient failure (e.g. a 503). The agent should retry."""
    return error_result(message, TRANSIENT, is_retryable=True)


def validation_error(message: str) -> dict[str, Any]:
    """A non-retryable input/lookup problem (e.g. unknown order). Ask/clarify."""
    return error_result(message, VALIDATION, is_retryable=False)


def business_error(message: str) -> dict[str, Any]:
    """A non-retryable business-rule failure (e.g. non-refundable order). Explain."""
    return error_result(message, BUSINESS, is_retryable=False)


def permission_error(message: str) -> dict[str, Any]:
    """A non-retryable authorization failure (e.g. order owned by another customer)."""
    return error_result(message, PERMISSION, is_retryable=False)
