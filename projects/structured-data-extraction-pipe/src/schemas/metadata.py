"""Document metadata schema — the forced-first-step contract (TR1).

`extract_metadata` runs via a **forced** `tool_choice` to guarantee a first step
(identify the document before enrichment). `doc_type` is an extensible enum, so an
unfamiliar document lands in `other` + detail rather than erroring.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

#: Extensible enum over the document types this pipeline knows, plus other/unclear.
DocType = Literal["invoice", "contract", "paper", "other", "unclear"]


class DocumentMetadata(BaseModel):
    """Basic identifying metadata extracted before type-specific enrichment."""

    doc_type: DocType = "unclear"
    doc_type_detail: Optional[str] = None
    language: Optional[str] = None
    dates: List[str] = Field(default_factory=list)  # ISO 8601 (TR3)
    field_confidence: Dict[str, float] = Field(default_factory=dict)
