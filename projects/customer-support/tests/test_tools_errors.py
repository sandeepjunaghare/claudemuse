"""Deterministic proof of the tools' TR6 error categories (no API).

Calls each tool's raw `.handler` directly (the decorated `SdkMcpTool` exposes it)
and drives the flaky 503 via the `force_transient_failures` seam, so error
categories are provable with zero API cost. The autouse `_reset_flaky` fixture
(conftest) keeps the probabilistic path off and clears the seam between cases.
"""

import asyncio

from mocks import fixtures
from tools.server import get_customer, lookup_order, process_refund


def _call(handler, args):
    return asyncio.run(handler(args))


def _category(result):
    return result.get("structuredContent", {}).get("errorCategory")


# --- lookup_order ----------------------------------------------------------


def test_lookup_order_transient_when_forced():
    """A forced 503 is reported as a (retryable) transient error."""
    fixtures.force_transient_failures(1)
    out = _call(lookup_order.handler, {"customer_id": "C001", "order_id": "O1001"})
    assert _category(out) == "transient"
    assert out["structuredContent"]["isRetryable"] is True


def test_lookup_order_transient_precedes_other_errors():
    """Transient is checked first: even an unknown order surfaces as transient when forced."""
    fixtures.force_transient_failures(1)
    out = _call(lookup_order.handler, {"customer_id": "C001", "order_id": "O9999"})
    assert _category(out) == "transient"


def test_lookup_order_unknown_is_validation():
    """An unknown order id is a non-retryable validation error."""
    out = _call(lookup_order.handler, {"customer_id": "C001", "order_id": "O9999"})
    assert _category(out) == "validation"
    assert out["structuredContent"]["isRetryable"] is False


def test_lookup_order_owner_mismatch_is_permission():
    """An order owned by a different customer is a non-retryable permission error."""
    out = _call(lookup_order.handler, {"customer_id": "C002", "order_id": "O1001"})
    assert _category(out) == "permission"
    assert out["structuredContent"]["isRetryable"] is False


def test_lookup_order_success_unchanged():
    """The happy path stays a non-error result (no error envelope)."""
    out = _call(lookup_order.handler, {"customer_id": "C001", "order_id": "O1001"})
    assert out.get("is_error") is False
    assert out["structuredContent"]["found"] is True


def test_lookup_order_two_forced_then_success():
    """Two consecutive forced 503s, then the success path (seam is a countdown)."""
    fixtures.force_transient_failures(2)
    assert _category(_call(lookup_order.handler, {"customer_id": "C001", "order_id": "O1001"})) == "transient"
    assert _category(_call(lookup_order.handler, {"customer_id": "C001", "order_id": "O1001"})) == "transient"
    out = _call(lookup_order.handler, {"customer_id": "C001", "order_id": "O1001"})
    assert out.get("is_error") is False


# --- process_refund --------------------------------------------------------


def test_process_refund_cancelled_is_business():
    """A refund against a cancelled order is a non-retryable business error."""
    out = _call(process_refund.handler, {"customer_id": "C001", "order_id": "O1004", "amount": 60.0})
    assert _category(out) == "business"
    assert out["structuredContent"]["isRetryable"] is False


def test_process_refund_over_total_is_business():
    """A refund amount exceeding the order total is a business error."""
    out = _call(process_refund.handler, {"customer_id": "C001", "order_id": "O1001", "amount": 999.0})
    assert _category(out) == "business"


def test_process_refund_success_unchanged():
    """An in-policy refund within the order total succeeds (no error)."""
    out = _call(process_refund.handler, {"customer_id": "C001", "order_id": "O1001", "amount": 42.0})
    assert out.get("is_error") is False
    assert out["structuredContent"]["refunded"] is True


# --- get_customer ----------------------------------------------------------


def test_get_customer_no_identifier_is_validation():
    """No identifier to search on is a validation error (ask for one; don't retry)."""
    out = _call(get_customer.handler, {})
    assert _category(out) == "validation"


def test_get_customer_single_match_not_error():
    """A single match is a verified success, not an error."""
    out = _call(get_customer.handler, {"email": "alice@example.com"})
    assert out.get("is_error") is False
    assert out["structuredContent"]["matchCount"] == 1


def test_get_customer_multi_match_not_error():
    """A multi-match (the John Smith pair) is the TR7 ask path, NOT an error."""
    out = _call(get_customer.handler, {"name": "John Smith"})
    assert out.get("is_error") is False
    assert out["structuredContent"]["matchCount"] == 2


def test_get_customer_zero_match_not_error():
    """A zero-match is a normal 'not found' result, not an error envelope."""
    out = _call(get_customer.handler, {"name": "Nobody Here"})
    assert out.get("is_error") is False
    assert out["structuredContent"]["matchCount"] == 0
