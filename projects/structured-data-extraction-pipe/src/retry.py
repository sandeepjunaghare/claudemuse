"""Validation-retry wrapper (TR4).

The critical distinction: **retry fixes format/structural errors; it does NOT recover
absent information.** A format error gets a capped retry-with-feedback loop; a
missing-info failure fails fast to human review — retrying it only burns tokens. The
extractor and validator are injectable so the loop is unit-testable offline with scripted
outputs (no API).
"""

import json
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import config
from schemas import FailureEnvelope
from validate import ValidationOutcome, validate as _default_validate


@dataclass
class RetryResult:
    """Outcome of the retry loop: the final validation outcome plus a failure envelope
    (None on success) and the resolved document type / attempt count."""

    outcome: ValidationOutcome
    doc_type: str
    failure: Optional[FailureEnvelope]
    attempts: int


def classify_failure(outcome: ValidationOutcome) -> str:
    """Map a failed validation outcome to `"retryable"` or `"fail_fast"`."""
    if outcome.error_type == "missing_info":
        return "fail_fast"
    return "retryable"  # "format" (and any unknown) → give retry a chance


def _feedback(raw: dict, detail: Optional[str]) -> str:
    """Build the retry feedback: the failed extraction + the specific error (TR4).
    (The original document is re-attached by `prompts.build_user_content`.)"""
    return (
        "Previous extraction that FAILED validation:\n"
        f"{json.dumps(raw, indent=2, default=str)}\n\n"
        f"{detail or 'Output did not match the schema.'}"
    )


# Extractor signature: (document, doc_type, feedback) -> (inferred_doc_type, raw_dict)
Extractor = Callable[[str, Optional[str], Optional[str]], Tuple[str, dict]]
Validator = Callable[[dict, str], ValidationOutcome]


def extract_with_retry(
    document: str,
    doc_type: Optional[str] = None,
    max_attempts: int = None,
    extractor: Optional[Extractor] = None,
    validator: Optional[Validator] = None,
) -> RetryResult:
    """Extract, validate, and retry format errors with feedback (capped). Fail fast on
    missing information.

    `extractor` defaults to `extract.extract_once`; `validator` to `validate.validate`.
    Both are injectable for testing.
    """
    max_attempts = max_attempts or config.MAX_RETRY_ATTEMPTS
    if extractor is None:
        from extract import extract_once

        def extractor(doc, dt, fb):  # noqa: E306 — local default binding
            return extract_once(doc, doc_type=dt, feedback=fb)

    validator = validator or _default_validate

    feedback: Optional[str] = None
    resolved_type = doc_type
    last: Optional[ValidationOutcome] = None
    last_raw: dict = {}

    for attempt in range(1, max_attempts + 1):
        inferred_type, raw = extractor(document, resolved_type, feedback)
        resolved_type = resolved_type or inferred_type  # pin the schema for subsequent retries
        last_raw = raw
        outcome = validator(raw, resolved_type)
        last = outcome

        if outcome.ok:
            return RetryResult(outcome, resolved_type, None, attempt)

        if classify_failure(outcome) == "fail_fast":
            return RetryResult(
                outcome,
                resolved_type,
                FailureEnvelope(type="missing_info", retryable=False, detail=outcome.error_detail or ""),
                attempt,
            )

        feedback = _feedback(last_raw, outcome.error_detail)  # retryable → loop with feedback

    # Format error survived the cap — route to human rather than loop forever.
    return RetryResult(
        last,
        resolved_type,
        FailureEnvelope(
            type="format",
            retryable=True,
            detail=f"Max retry attempts ({max_attempts}) exhausted. Last error: "
            f"{last.error_detail if last else 'unknown'}",
        ),
        max_attempts,
    )
