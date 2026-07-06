"""Pydantic extraction schemas — the single source of truth.

Every document type has one Pydantic model here; the JSON Schema handed to
`tool_use` is generated from it via `model_json_schema()` (see `extract.build_tool`),
so the extraction contract and the validation logic can never drift apart.
"""

from schemas.base import ExtractionResult, FailureEnvelope, Route
from schemas.contract import Contract, ContractCategory
from schemas.invoice import Invoice, LineItem
from schemas.metadata import DocType, DocumentMetadata
from schemas.paper import Paper

#: doc_type string -> Pydantic model. The router and batch reconciler key off this.
SCHEMA_REGISTRY = {
    "invoice": Invoice,
    "contract": Contract,
    "paper": Paper,
    "metadata": DocumentMetadata,
}

__all__ = [
    "ExtractionResult",
    "FailureEnvelope",
    "Route",
    "Invoice",
    "LineItem",
    "Contract",
    "ContractCategory",
    "Paper",
    "DocumentMetadata",
    "DocType",
    "SCHEMA_REGISTRY",
]
