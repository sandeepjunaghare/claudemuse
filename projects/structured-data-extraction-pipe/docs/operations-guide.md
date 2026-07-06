# Operations Guide — Structured Data Extraction Pipeline

How to install, run, and test the pipeline. It uses the plain `anthropic` SDK (Messages API
`tool_use` + Message Batches API) with Pydantic as the single source of truth — **not** the
Claude Agent SDK.

## Prerequisites

| Requirement | Value |
|---|---|
| Python | 3.10 via the **shared monorepo venv** `../../.venv` (no per-project venv) |
| API key | `ANTHROPIC_API_KEY` in the **monorepo-root `.env`** (two levels up); loaded by `src/config.py` |
| Dependencies | `anthropic`, `pydantic`, `pytest`, `python-dotenv` |

The raw `anthropic` SDK authenticates only via `ANTHROPIC_API_KEY` — there is no `claude`
CLI fallback. Offline unit tests need no key; live/batch calls do.

## Install

```bash
cd projects/structured-data-extraction-pipe
../../.venv/bin/pip install -r requirements.txt
```

(The shared venv already has these; this is a no-op if so.)

## Run a single document (live)

```bash
../../.venv/bin/python run_example.py
```

Extracts the seeded bad-sum invoice and prints the `ExtractionResult` (doc type, validity,
`conflict_detected`, route, confidence, data). Prints a notice and exits if no key is set.

Programmatic entry point:

```python
import sys; sys.path.insert(0, "src")
from pipeline import extract_document
result = extract_document(document_text, doc_type=None)   # doc_type optional; None => router picks
# result.data / result.valid / result.conflict_detected / result.confidence / result.route / result.failure
```

## Batch processing (live, high volume)

```python
from batch import BatchDoc, submit_batch, wait_for_batch, collect_batch, resubmit_failed

docs = [BatchDoc(custom_id="doc-0", document=text0, doc_type="invoice"), ...]
batch_id = submit_batch(docs)
wait_for_batch(batch_id)                 # polls until processing_status == "ended"
rec = collect_batch(batch_id)            # reconciles by custom_id
new_id, resubmitted = resubmit_failed(docs, rec)   # resubmits ONLY failures (chunks oversized)
```

Batches are ~50% cheaper and finish within ≤24h. They do **not** support multi-turn tool
calling, so each request is a single-shot extraction (retry-with-feedback is the interactive
path). Results arrive unordered — always key by `custom_id`.

## Tests

```bash
# Offline regression gate — no key, no network (run before any prompt/schema change):
../../.venv/bin/python -m pytest -m "not integration"

# Live integration — real API + a >=100-doc Batch run (needs a key; spends tokens, up to 24h):
../../.venv/bin/python -m pytest -m integration
```

The offline suite (45 tests) asserts on structure: schema validity, null-not-fabricated,
novel→other, bad-sum flagged / clean not, retry-fixes-format + missing-info-fails-fast, batch
reconcile by `custom_id`, and per-type/per-field audit. Treat it as the regression gate.

## Accuracy audit

```python
import audit
report = audit.stratified_report([{"doc_type": ..., "expected": {...}, "actual": {...}}, ...])
print(audit.format_report(report))    # accuracy by type AND field — never a lone aggregate
```

## Layout

```
src/schemas/     Pydantic models = single source of truth (JSON Schema generated from these)
src/extract.py   tool_use extraction + router (tool_choice: any vs forced)
src/validate.py  Pydantic structural + business-rule validation (conflict, missing-info)
src/retry.py     validation-retry loop; retryable (format) vs fail-fast (missing info)
src/confidence.py field-level confidence + calibrated routing
src/batch.py     Message Batches submitter + custom_id partial-failure recovery
src/pipeline.py  extract_document(): the end-to-end interactive entry point
src/prompts.py   normalization rules + never-fabricate contract
src/fewshot.py   layout examples (inline vs bibliography; narrative vs table)
src/audit.py     stratified accuracy report (by type AND field)
data/corpus.py   labeled validation set (ground truth) + seeded edge-case samples
tests/           regression gate (offline) + gated integration tests
```
