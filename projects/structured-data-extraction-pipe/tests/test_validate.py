"""Phase 2: Pydantic + business-rule validation — conflict, missing-info, format (TR4/TR5)."""

import validate


def test_clean_invoice_is_valid_and_not_flagged():
    raw = {"vendor": "Acme", "stated_total": 80.0, "calculated_total": 80.0,
           "line_items": [{"amount": 50.0}, {"amount": 30.0}]}
    out = validate.validate(raw, "invoice")
    assert out.ok is True
    assert out.conflict_detected is False  # FR3: clean invoices are never flagged


def test_bad_sum_invoice_is_valid_but_flagged():
    raw = {"vendor": "Globex", "stated_total": 1080.0, "calculated_total": 980.0}
    out = validate.validate(raw, "invoice")
    assert out.ok is True  # structurally fine — the conflict is a flag, not a failure
    assert out.conflict_detected is True  # TR5: calculated != stated


def test_conflict_respects_tolerance():
    raw = {"stated_total": 80.0, "calculated_total": 80.005}
    assert validate.validate(raw, "invoice").conflict_detected is False


def test_absent_field_returns_null_not_fabricated():
    raw = {"vendor": "Initech", "stated_total": 300.0, "calculated_total": 300.0}
    out = validate.validate(raw, "invoice")
    assert out.ok is True
    assert out.instance.po_number is None  # FR2


def test_format_error_is_retryable():
    # A comma-formatted number the schema can't coerce → structural/format failure.
    raw = {"vendor": "Stark", "stated_total": "12,500.00"}
    out = validate.validate(raw, "invoice")
    assert out.ok is False
    assert out.error_type == "format"
    assert out.error_detail  # carries the specific error for retry feedback


def test_missing_info_is_fail_fast():
    raw = {"title": "Scaling Laws Revisited", "authors": ["Smith et al."]}
    out = validate.validate(raw, "paper")
    assert out.ok is False
    assert out.error_type == "missing_info"
