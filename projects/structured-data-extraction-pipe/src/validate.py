"""Validation: structural (Pydantic) + business rules (TR4/TR5).

Two kinds of failure, and the distinction is the whole point:
- **format** — the raw JSON doesn't satisfy the schema's types/shape (a comma in a
  number, a mis-typed field). A retry with feedback can fix it.
- **missing_info** — the structure is fine, but the document genuinely does not contain
  the information ("Smith et al." instead of the author list; "see attached"). No retry
  can recover it; it must fail fast to human review.

Arithmetic conflict (`stated_total != calculated_total`) is neither a failure nor
retryable — it's a *flag* on an otherwise-valid extraction (TR5/FR3).
"""

from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, ValidationError

from schemas import SCHEMA_REGISTRY

#: Phrases that signal information is present elsewhere / truncated — not extractable
#: from this document, so retrying is futile (TR4). Kept tight to avoid false positives.
_MISSING_INFO_MARKERS = (
    "et al",
    "see attached",
    "see appendix",
    "provided separately",
    "in a separate document",
)


@dataclass
class ValidationOutcome:
    """Result of validating one raw extraction.

    `ok` is True when the extraction is usable (structurally valid AND no missing-info
    failure); a conflicting-but-valid invoice is still `ok=True` — the conflict is a flag,
    not a failure. `error_type` is `"format"` (retryable) or `"missing_info"` (fail fast).
    """

    ok: bool
    instance: Optional[BaseModel] = None
    conflict_detected: bool = False
    error_type: Optional[str] = None  # "format" | "missing_info"
    error_detail: Optional[str] = None


def _find_missing_info(instance: BaseModel) -> Optional[str]:
    """Scan string / list-of-string fields for a missing-info marker; return a detail or None."""
    for field_name, value in instance.__dict__.items():
        values: List[str] = []
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = [v for v in value if isinstance(v, str)]
        for v in values:
            lowered = v.lower()
            for marker in _MISSING_INFO_MARKERS:
                if marker in lowered:
                    return (
                        f"Field '{field_name}' contains {marker!r} ({v!r}); the full "
                        f"information is not present in this document."
                    )
    return None


def validate(raw: dict, doc_type: str) -> ValidationOutcome:
    """Validate a raw extraction against its schema and business rules."""
    model_cls = SCHEMA_REGISTRY[doc_type]
    try:
        instance = model_cls.model_validate(raw)
    except ValidationError as exc:
        return ValidationOutcome(
            ok=False,
            error_type="format",
            error_detail=_format_pydantic_error(exc),
        )

    missing = _find_missing_info(instance)
    if missing is not None:
        return ValidationOutcome(
            ok=False,
            instance=instance,
            error_type="missing_info",
            error_detail=missing,
        )

    conflict = instance.conflict() if hasattr(instance, "conflict") else False
    return ValidationOutcome(ok=True, instance=instance, conflict_detected=conflict)


def _format_pydantic_error(exc: ValidationError) -> str:
    """Render a Pydantic error compactly for retry feedback — the *specific* problem (TR4)."""
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']} (got {err.get('input')!r})")
    return "Validation errors:\n" + "\n".join(lines)
