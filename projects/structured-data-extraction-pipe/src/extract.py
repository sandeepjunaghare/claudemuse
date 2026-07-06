"""Extraction via `tool_use` + the router (TR1).

`tool_use` with a Pydantic-derived JSON Schema is the extraction contract: it guarantees
the model returns valid, well-typed JSON. It does **not** guarantee the values are right —
that's what `validate.py` / `retry.py` / `confidence.py` are for.

The **router** is the single tool-choice decision point:
- document type unknown  -> `tool_choice: {"type": "any"}` over the competing content
  schemas; the tool the model picks *is* the inferred type.
- document type known    -> forced `tool_choice: {"type": "tool", "name": ...}` to
  guarantee the step (e.g. `extract_metadata` as a forced first step before enrichment).
"""

from typing import List, Optional, Tuple

import config
import fewshot
import prompts
from schemas import SCHEMA_REGISTRY

#: Content schemas that compete when the document type is unknown (metadata is a
#: separate forced-first-step tool, not a competitor).
CONTENT_TYPES = ["invoice", "contract", "paper"]

_TOOL_DESCRIPTIONS = {
    "invoice": "Extract structured data from an invoice (vendor, line items, totals, dates).",
    "contract": "Extract structured data from a contract (parties, dates, term, category).",
    "paper": "Extract structured data from a research paper (title, authors, references, sections).",
    "metadata": "Identify a document's basic metadata: type, language, and dates.",
}


class ExtractionError(RuntimeError):
    """Raised when the model does not return a usable tool_use block (e.g. a refusal)."""


def tool_name_for(doc_type: str) -> str:
    """`invoice` -> `extract_invoice`."""
    return f"extract_{doc_type}"


def doc_type_from_tool_name(name: str) -> str:
    """`extract_invoice` -> `invoice`."""
    return name[len("extract_") :] if name.startswith("extract_") else name


def build_tool(doc_type: str) -> dict:
    """Build one `tool_use` tool definition from its Pydantic model.

    The `input_schema` is generated via `model_json_schema()` — the single source of
    truth. We deliberately do NOT set `strict: true`: strict output forbids the numeric
    and length constraints Pydantic emits, and the design intent is that the schema gives
    the *syntactic* guarantee while Pydantic does *semantic* validation afterward.
    """
    model_cls = SCHEMA_REGISTRY[doc_type]
    return {
        "name": tool_name_for(doc_type),
        "description": _TOOL_DESCRIPTIONS[doc_type],
        "input_schema": model_cls.model_json_schema(),
    }


def all_content_tools() -> List[dict]:
    """Tool defs for the competing content schemas (invoice/contract/paper)."""
    return [build_tool(t) for t in CONTENT_TYPES]


def all_tools() -> List[dict]:
    """Every tool def, including `extract_metadata` and the few-shot tools."""
    return [build_tool(t) for t in SCHEMA_REGISTRY]


def route(doc_type: Optional[str]) -> Tuple[List[dict], dict]:
    """Pick (tools, tool_choice) for a document. See module docstring for the policy."""
    if doc_type is None:
        return all_content_tools(), {"type": "any"}
    if doc_type not in SCHEMA_REGISTRY:
        raise KeyError(f"Unknown doc_type {doc_type!r}; known: {sorted(SCHEMA_REGISTRY)}")
    return all_tools(), {"type": "tool", "name": tool_name_for(doc_type)}


def _extract_tool_use(response) -> Tuple[str, dict]:
    """Pull the (tool_name, input) from a Messages API response, guarding refusals."""
    if getattr(response, "stop_reason", None) == "refusal":
        raise ExtractionError("Model refused the extraction request.")
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.name, dict(block.input)
    raise ExtractionError(
        f"No tool_use block in response (stop_reason={getattr(response, 'stop_reason', None)})."
    )


def extract_once(
    document: str,
    doc_type: Optional[str] = None,
    feedback: Optional[str] = None,
    model: Optional[str] = None,
    include_fewshot: bool = True,
    client=None,
) -> Tuple[str, dict]:
    """One extraction call. Returns (inferred_doc_type, raw_extracted_dict).

    `raw_extracted_dict` is syntactically guaranteed by `tool_use` but not yet validated
    — pass it to `validate.py`. `client` is injectable for testing; it defaults to the
    real Anthropic client from `config.get_client()`.
    """
    client = client or config.get_client()
    tools, tool_choice = route(doc_type)
    examples = fewshot.example_messages() if include_fewshot else None
    messages = prompts.build_messages(document, feedback, examples)

    response = client.messages.create(
        model=model or config.EXTRACTION_MODEL,
        max_tokens=config.EXTRACTION_MAX_TOKENS,
        system=prompts.SYSTEM_PROMPT,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
    )
    tool_name, raw = _extract_tool_use(response)
    return doc_type_from_tool_name(tool_name), raw
