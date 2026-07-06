"""Message Batches API submitter with per-doc failure recovery (TR7).

The Batch API is ~50% cheaper and processes large volumes within a ≤24h window, but it
does **not** support multi-turn tool calling — so each request is a single-shot
extraction (no in-batch retry-with-feedback). Requests are correlated by `custom_id`;
results arrive in **any order**, so everything reconciles by `custom_id`, never position.
On partial failure, only the failed docs are resubmitted (oversized ones chunked).

`reconcile` is a pure function over result records, so the recovery logic is unit-tested
offline with mocked, out-of-order results.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import config
import fewshot
import prompts
from extract import ExtractionError, _extract_tool_use, doc_type_from_tool_name, route


@dataclass
class BatchDoc:
    """A document queued for batch extraction, correlated by `custom_id`."""

    custom_id: str
    document: str
    doc_type: Optional[str] = None


@dataclass
class BatchReconciliation:
    """The result of reconciling batch results by `custom_id`."""

    succeeded: Dict[str, dict] = field(default_factory=dict)  # custom_id -> {doc_type, raw}
    failed: Dict[str, str] = field(default_factory=dict)  # custom_id -> reason

    @property
    def failed_ids(self) -> List[str]:
        return list(self.failed)


def build_request(doc: BatchDoc, model: Optional[str] = None) -> dict:
    """Build one batch request `{custom_id, params}` — a single-shot tool_use extraction."""
    tools, tool_choice = route(doc.doc_type)
    messages = prompts.build_messages(doc.document, feedback=None, example_messages=fewshot.example_messages())
    return {
        "custom_id": doc.custom_id,
        "params": {
            "model": model or config.EXTRACTION_MODEL,
            "max_tokens": config.EXTRACTION_MAX_TOKENS,
            "system": prompts.SYSTEM_PROMPT,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        },
    }


def chunk_document(text: str, max_chars: int = 40_000) -> List[str]:
    """Split an oversized document into ≤`max_chars` chunks on paragraph boundaries (TR7).

    A document too large for one request is chunked and resubmitted as several docs; the
    caller stitches the partial extractions. Small documents pass through unchanged.
    """
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def submit_batch(docs: List[BatchDoc], client=None, model: Optional[str] = None) -> str:
    """Create a batch of single-shot extraction requests; return the batch id."""
    client = client or config.get_client()
    requests = [build_request(d, model=model) for d in docs]
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def wait_for_batch(batch_id: str, client=None, poll_interval: Optional[int] = None, max_wait_seconds: int = 24 * 3600):
    """Poll until the batch's `processing_status == "ended"`; return the final batch object."""
    client = client or config.get_client()
    poll_interval = poll_interval or config.BATCH_POLL_INTERVAL_SECONDS
    waited = 0
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return batch
        if waited >= max_wait_seconds:
            raise TimeoutError(f"Batch {batch_id} did not end within {max_wait_seconds}s.")
        time.sleep(poll_interval)
        waited += poll_interval


def reconcile(results: Iterable) -> BatchReconciliation:
    """Reconcile batch result records by `custom_id` (pure — no network).

    A result is `succeeded` (extract its tool_use input), or one of `errored` / `expired`
    / `canceled` (recorded as failed for resubmission). A succeeded result that somehow
    lacks a tool_use block is also treated as failed.
    """
    rec = BatchReconciliation()
    for r in results:
        cid = r.custom_id
        rtype = r.result.type
        if rtype == "succeeded":
            try:
                tool_name, raw = _extract_tool_use(r.result.message)
                rec.succeeded[cid] = {"doc_type": doc_type_from_tool_name(tool_name), "raw": raw}
            except ExtractionError as exc:
                rec.failed[cid] = f"no_tool_use:{exc}"
        else:
            rec.failed[cid] = rtype
    return rec


def collect_batch(batch_id: str, client=None) -> BatchReconciliation:
    """Stream a completed batch's results and reconcile them by `custom_id`."""
    client = client or config.get_client()
    results = client.messages.batches.results(batch_id)
    return reconcile(results)


def resubmit_failed(
    docs: List[BatchDoc],
    reconciliation: BatchReconciliation,
    client=None,
    model: Optional[str] = None,
) -> Tuple[Optional[str], List[BatchDoc]]:
    """Resubmit ONLY the failed docs (chunking oversized ones). Returns (new_batch_id,
    resubmitted_docs). Returns (None, []) when there were no failures."""
    by_id = {d.custom_id: d for d in docs}
    failed_docs: List[BatchDoc] = []
    for cid in reconciliation.failed_ids:
        original = by_id.get(cid)
        if original is None:
            continue
        chunks = chunk_document(original.document)
        if len(chunks) == 1:
            failed_docs.append(original)
        else:
            for i, chunk in enumerate(chunks):
                failed_docs.append(BatchDoc(f"{cid}::chunk{i}", chunk, original.doc_type))
    if not failed_docs:
        return None, []
    return submit_batch(failed_docs, client=client, model=model), failed_docs
