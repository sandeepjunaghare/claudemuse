"""Phase 2: retry fixes format errors but fails fast on missing info (TR4).

Both critical behaviors are demonstrated here with a scripted extractor (no API): a format
error fixed on retry-with-feedback, and a missing-info case that fails fast without looping.
"""

import retry
import validate
from validate import ValidationOutcome


class ScriptedExtractor:
    """Returns a queued (doc_type, raw) per call; records how many times it was called."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.feedbacks = []

    def __call__(self, document, doc_type, feedback):
        self.feedbacks.append(feedback)
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return out


def test_classify_failure():
    assert retry.classify_failure(ValidationOutcome(ok=False, error_type="format")) == "retryable"
    assert retry.classify_failure(ValidationOutcome(ok=False, error_type="missing_info")) == "fail_fast"


def test_format_error_fixed_on_retry():
    bad = ("invoice", {"vendor": "Stark", "stated_total": "12,500.00"})   # comma → format error
    good = ("invoice", {"vendor": "Stark", "stated_total": 12500.0, "calculated_total": 12500.0})
    extractor = ScriptedExtractor([bad, good])

    result = retry.extract_with_retry("doc", extractor=extractor, validator=validate.validate, max_attempts=3)

    assert result.outcome.ok is True
    assert result.failure is None
    assert result.attempts == 2  # fixed on the second try
    assert extractor.feedbacks[1] is not None  # the retry carried feedback


def test_missing_info_fails_fast_without_looping():
    etal = ("paper", {"title": "Scaling Laws Revisited", "authors": ["Smith et al."]})
    extractor = ScriptedExtractor([etal, etal, etal])

    result = retry.extract_with_retry("doc", extractor=extractor, validator=validate.validate, max_attempts=3)

    assert result.failure is not None
    assert result.failure.type == "missing_info"
    assert result.failure.retryable is False
    assert extractor.calls == 1  # did NOT retry missing information


def test_format_error_respects_attempt_cap():
    bad = ("invoice", {"stated_total": "not-a-number"})
    extractor = ScriptedExtractor([bad])  # always bad

    result = retry.extract_with_retry("doc", extractor=extractor, validator=validate.validate, max_attempts=3)

    assert result.failure is not None
    assert result.failure.type == "format"
    assert result.attempts == 3
    assert extractor.calls == 3  # capped — no runaway loop


def test_doc_type_is_pinned_after_inference():
    good = ("invoice", {"vendor": "Acme", "stated_total": 80.0, "calculated_total": 80.0})
    extractor = ScriptedExtractor([good])
    result = retry.extract_with_retry("doc", doc_type=None, extractor=extractor, validator=validate.validate)
    assert result.doc_type == "invoice"
