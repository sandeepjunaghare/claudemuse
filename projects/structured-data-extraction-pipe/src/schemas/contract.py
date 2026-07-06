"""Contract extraction schema. Demonstrates the extensible enum (TR2) + ISO dates (TR3)."""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

#: Extensible enum: known categories plus `other` (novel — pair with `category_detail`)
#: and `unclear` (ambiguous). A category we've never seen is captured, never dropped.
ContractCategory = Literal[
    "nda",
    "service_agreement",
    "employment",
    "lease",
    "purchase",
    "license",
    "other",
    "unclear",
]


class Contract(BaseModel):
    """Structured contract. `category` is an extensible enum; `category_detail` carries the
    free-text label when `category == "other"`."""

    parties: List[str] = Field(default_factory=list)
    effective_date: Optional[str] = None  # ISO 8601 (TR3)
    term: Optional[str] = None
    governing_law: Optional[str] = None
    category: ContractCategory = "unclear"
    category_detail: Optional[str] = None
    field_confidence: Dict[str, float] = Field(default_factory=dict)
