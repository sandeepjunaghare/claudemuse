"""End-to-end single-document pipeline: extract -> validate/retry -> route (PRD API).

`extract_document` is the public entry point. It threads the injectable client through
the retry loop, assembles the `ExtractionResult` envelope, and applies confidence/conflict
routing. Batch processing is the volume path (`batch.py`); this is the interactive one.
"""

from typing import Optional

import confidence as conf
from retry import extract_with_retry
from schemas import ExtractionResult


def extract_document(
    document: str,
    doc_type: Optional[str] = None,
    client=None,
    threshold: float = None,
) -> ExtractionResult:
    """Run one document through the full pipeline and return a validated result envelope."""
    from extract import extract_once

    def extractor(doc, dt, feedback):
        return extract_once(doc, doc_type=dt, feedback=feedback, client=client)

    result = extract_with_retry(document, doc_type=doc_type, extractor=extractor)
    return assemble_result(result, threshold)


def assemble_result(retry_result, threshold: float = None) -> ExtractionResult:
    """Turn a `RetryResult` into the public `ExtractionResult`, applying routing (pure)."""
    outcome = retry_result.outcome
    instance = outcome.instance
    data = instance.model_dump() if instance is not None else None
    field_confidence = dict(getattr(instance, "field_confidence", {}) or {})
    route = conf.route_decision(
        field_confidence,
        outcome.conflict_detected,
        retry_result.failure,
        threshold,
    )
    return ExtractionResult(
        doc_type=retry_result.doc_type,
        data=data,
        valid=outcome.ok,
        conflict_detected=outcome.conflict_detected,
        confidence=field_confidence,
        route=route,
        failure=retry_result.failure,
    )
