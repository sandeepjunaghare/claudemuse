"""Invoice extraction schema, with the arithmetic self-correction contract (TR5).

The model extracts `line_items`, `stated_total` (what the page says), and a
model-summed `calculated_total`. It does **not** decide `conflict_detected` — that flag
is computed deterministically from those two numbers (see `conflict()` / `validate.py`),
so a clean invoice is never flagged and a bad-sum one always is (FR3).
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """One invoice line. Every field is optional — a messy line may omit any of them (FR2)."""

    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class Invoice(BaseModel):
    """Structured invoice. Maybe-absent fields are nullable; nothing is required, so the
    model never fabricates a value to satisfy the schema (TR2)."""

    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO 8601 (normalized in the prompt — TR3)
    due_date: Optional[str] = None  # ISO 8601
    po_number: Optional[str] = None
    currency: Optional[str] = None  # ISO 4217, e.g. "USD"
    line_items: List[LineItem] = Field(default_factory=list)
    stated_total: Optional[float] = None  # the total printed on the page
    calculated_total: Optional[float] = None  # model-summed from line items (TR5)
    field_confidence: Dict[str, float] = Field(default_factory=dict)

    def conflict(self, tolerance: float = 0.01) -> bool:
        """True iff stated and calculated totals disagree (TR5). Both must be present —
        an absent total is a coverage gap for routing, not an arithmetic conflict."""
        if self.stated_total is None or self.calculated_total is None:
            return False
        return abs(self.stated_total - self.calculated_total) > tolerance
