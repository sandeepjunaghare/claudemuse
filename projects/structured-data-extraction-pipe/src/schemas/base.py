"""Shared contracts: the result envelope and the extensible-enum convention (TR2/TR8).

The **extensible enum** is the resilience pattern the exam probes: every categorical
field is a `Literal[..., "other", "unclear"]` paired with a `*_detail` string. A novel
category lands in `"other"` + detail rather than being dropped or erroring (FR2/TR2);
genuine ambiguity lands in `"unclear"`.

`field_confidence` (a field on every extraction model) is the model's self-reported
per-field confidence in `[0, 1]` — the raw signal `confidence.py` calibrates and routes on.
"""

from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field

#: Where a document goes after extraction (FR5).
Route = Literal["auto_accept", "human_review"]


class FailureEnvelope(BaseModel):
    """Structured failure surfaced to the human-review queue (TR4).

    `retryable` distinguishes a format/structural error (a retry might fix it) from a
    genuinely-missing-information failure (retrying only burns tokens — fail fast).
    """

    type: str
    retryable: bool
    detail: str


class ExtractionResult(BaseModel):
    """The public output of the pipeline (PRD API surface).

    `data` is the schema-valid extracted JSON (with `null` for absent fields, never
    fabricated). `conflict_detected` is the arithmetic self-correction flag (TR5),
    computed deterministically — never trusted from the model.
    """

    doc_type: Optional[str] = None
    data: Optional[dict] = None
    valid: bool = False
    conflict_detected: bool = False
    confidence: Dict[str, float] = Field(default_factory=dict)
    route: Route = "human_review"
    failure: Optional[FailureEnvelope] = None
