"""Phase 4: confidence + conflict routing, and threshold calibration (TR8/FR5)."""

import confidence
from schemas import FailureEnvelope


def test_high_confidence_clean_doc_auto_accepts():
    assert confidence.route_decision({"vendor": 0.95, "stated_total": 0.99}, False) == "auto_accept"


def test_low_confidence_routes_to_human():
    assert confidence.route_decision({"vendor": 0.95, "effective_date": 0.4}, False) == "human_review"


def test_conflict_always_routes_to_human():
    assert confidence.route_decision({"vendor": 0.99}, conflict_detected=True) == "human_review"


def test_failure_always_routes_to_human():
    fail = FailureEnvelope(type="missing_info", retryable=False, detail="et al.")
    assert confidence.route_decision({"title": 0.99}, False, failure=fail) == "human_review"


def test_empty_confidence_auto_accepts_when_clean():
    assert confidence.route_decision({}, False) == "auto_accept"


def test_calibrate_separates_correct_from_incorrect():
    samples = [(0.92, True), (0.88, True), (0.95, True), (0.30, False), (0.45, False)]
    threshold = confidence.calibrate(samples)
    assert 0.45 < threshold <= 0.88
    # Routing at the calibrated threshold: correct auto-accept, incorrect route to review.
    for conf, correct in samples:
        route = confidence.route_decision({"f": conf}, False, threshold=threshold)
        assert (route == "auto_accept") == correct
