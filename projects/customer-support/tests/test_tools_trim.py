"""Deterministic proof of the TR9b output TRIM (no API).

`lookup_order` is backed by a 40+-field verbose record but must expose only the
~5 fields that matter. Tests call the tool's `.handler` directly and assert the
content text + structuredContent contain ONLY the kept fields, that the verbose
tail never appears, and that the TR5 date-format + the success-text parse
contract (which `normalize_order_dates` and `case_facts_recorder` rely on) are
intact. The autouse `_reset_flaky` fixture pins the 503 path off.
"""

import pytest

from mocks import fixtures
from tools.server import lookup_order

#: Verbose field markers that must NEVER leak to the model.
_VERBOSE_MARKERS = (
    "warehouse", "risk_score", "internal_flags", "ip_address", "payment_last4",
    "user_agent", "fulfillment_center", "billing_zip", "loyalty_tier", "subtotal",
)


async def _lookup(order_id="O1001", customer_id="C001"):
    fixtures.reset_flaky()
    return await lookup_order.handler({"customer_id": customer_id, "order_id": order_id})


async def test_backing_record_is_verbose():
    """Sanity: the source record really is bloated (so the trim is meaningful)."""
    assert len(fixtures.get_order_verbose("O1001")) >= 40


async def test_trim_exposes_only_kept_structured_fields():
    out = await _lookup()
    sc = out["structuredContent"]
    assert set(sc.keys()) <= {"found", "orderId", "status", "total", "placedAt", "trackingNumber"}
    assert len(sc) <= 7
    assert sc["orderId"] == "O1001"
    assert sc["status"] == "shipped"
    assert sc["total"] == 42.0
    assert sc["trackingNumber"]  # the one genuinely-useful extra is kept


async def test_verbose_fields_absent_from_content_and_structured():
    out = await _lookup()
    text = out["content"][0]["text"].lower()
    blob = str(out["structuredContent"]).lower()
    for marker in _VERBOSE_MARKERS:
        assert marker not in text, marker
        assert marker not in blob, marker


async def test_success_text_parse_contract_intact():
    """The `Order ...: status ..., total $..., placed <date>.` contract is unchanged,
    with the date as the FINAL segment (so TR5 normalize + the recorder keep working).
    """
    out = await _lookup()
    text = out["content"][0]["text"]
    assert text.startswith("Order O1001: status shipped, total $42.00, placed ")
    assert text.rstrip().endswith(".")
    # Heterogeneous date preserved verbatim in the text for the TR5 hook to normalize.
    assert "1740787200" in text


@pytest.mark.parametrize("order_id,total", [("O1002", 900.0), ("O1003", 120.0)])
async def test_trim_consistent_across_orders(order_id, total):
    out = await _lookup(order_id=order_id, customer_id=fixtures.get_order(order_id)["customer_id"])
    sc = out["structuredContent"]
    assert sc["orderId"] == order_id
    assert sc["total"] == total
    assert set(sc.keys()) <= {"found", "orderId", "status", "total", "placedAt", "trackingNumber"}
