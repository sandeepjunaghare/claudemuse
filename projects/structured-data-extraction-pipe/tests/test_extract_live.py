"""Live integration: real extraction against the Anthropic API (needs ANTHROPIC_API_KEY).

Run with:  ../../.venv/bin/python -m pytest -m integration
Skipped automatically when no key is present. Spends a small number of tokens.
"""

import pytest

import config

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not config.anthropic_key_present(), reason="No ANTHROPIC_API_KEY for live run."),
]


def test_novel_category_lands_in_other():
    from data.corpus import SAMPLES
    from pipeline import extract_document

    res = extract_document(SAMPLES["novel_category_contract"], doc_type="contract")
    assert res.doc_type == "contract"
    assert res.data["category"] == "other"  # novel category captured, not dropped/errored
    assert res.data.get("category_detail")


def test_absent_field_returns_null_not_fabricated():
    from data.corpus import SAMPLES
    from pipeline import extract_document

    res = extract_document(SAMPLES["absent_field_invoice"], doc_type="invoice")
    assert res.valid is True
    assert res.data["po_number"] is None  # FR2: never fabricated


def test_bad_sum_flagged_and_routed():
    from data.corpus import SAMPLES
    from pipeline import extract_document

    res = extract_document(SAMPLES["bad_sum_invoice"], doc_type="invoice")
    assert res.conflict_detected is True  # TR5
    assert res.route == "human_review"


def test_clean_invoice_not_flagged():
    from pipeline import extract_document

    clean = (
        "INVOICE 1042 Vendor: Acme Corp Date: 2026-02-10 PO: PO-8891\n"
        "2 x Widget @ 25.00 = 50.00\n1 x Gadget @ 30.00 = 30.00\nTotal: $80.00 USD"
    )
    res = extract_document(clean, doc_type="invoice")
    assert res.valid is True
    assert res.conflict_detected is False  # FR3: clean invoices are never flagged
