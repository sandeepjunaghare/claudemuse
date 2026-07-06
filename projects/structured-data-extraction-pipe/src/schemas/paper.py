"""Research-paper extraction schema.

Handles inline-citation vs bibliography layouts via few-shot (TR6). `authors` is where
the missing-info-fails-fast case lives (TR4): a source that says "Smith et al." does not
contain the full author list, so it must fail fast to review rather than loop on retry.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """Structured research paper. Absent authors return `[]` / `null`, never a fabricated name."""

    title: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    references: List[str] = Field(default_factory=list)
    sections: List[str] = Field(default_factory=list)
    publication_date: Optional[str] = None  # ISO 8601
    field_confidence: Dict[str, float] = Field(default_factory=dict)
