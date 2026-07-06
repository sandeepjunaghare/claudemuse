"""The pipeline spine: RetryResult -> ExtractionResult with routing applied (pure, no API)."""

from pipeline import assemble_result
from retry import RetryResult
from schemas import FailureEnvelope
from validate import ValidationOutcome, validate


def test_clean_result_auto_accepts():
    out = validate(
        {"vendor": "Acme", "stated_total": 80.0, "calculated_total": 80.0,
         "field_confidence": {"vendor": 0.99, "stated_total": 0.98}},
        "invoice",
    )
    res = assemble_result(RetryResult(out, "invoice", None, 1))
    assert res.valid is True
    assert res.conflict_detected is False
    assert res.route == "auto_accept"
    assert res.data["vendor"] == "Acme"
    assert res.confidence["vendor"] == 0.99


def test_conflict_routes_to_human():
    out = validate(
        {"stated_total": 1080.0, "calculated_total": 980.0, "field_confidence": {"stated_total": 0.99}},
        "invoice",
    )
    res = assemble_result(RetryResult(out, "invoice", None, 1))
    assert res.conflict_detected is True
    assert res.route == "human_review"


def test_failure_result_routes_to_human_with_no_data():
    out = ValidationOutcome(ok=False, error_type="missing_info", error_detail="et al.")
    failure = FailureEnvelope(type="missing_info", retryable=False, detail="et al.")
    res = assemble_result(RetryResult(out, "paper", failure, 1))
    assert res.valid is False
    assert res.data is None
    assert res.failure is not None
    assert res.route == "human_review"
