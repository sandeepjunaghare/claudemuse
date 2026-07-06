# Todo — Structured Data Extraction Pipeline

> Built with the plain `anthropic` SDK (Messages API `tool_use` + Message Batches API) +
> Pydantic. Offline unit tests are the regression gate; live API/Batch calls live in gated
> `integration`-marked tests. Spec: `docs/03-structured-data-extraction-pipeline.md` (FR1–FR5,
> TR1–TR8); PRD: `docs/03-structured-data-extraction-prd.md`.

## Phase 1 — Schema extraction (TR1/TR2/TR3)
- [x] `requirements.txt`, `pytest.ini` (`integration` marker; no asyncio), `src/config.py`
- [x] Pydantic schemas (invoice/contract/paper/metadata) — single source of truth; nullable + extensible enum
- [x] `extract.py`: `build_tool` (schema from `model_json_schema()`), router (`any` vs forced `tool_choice`)
- [x] `prompts.py`: normalization rules + never-fabricate + other/unclear; `run_example.py`
- [x] Validate: absent → null; novel → other+detail; output always validates (`test_schemas`, `test_extract_router`)

## Phase 2 — Validate + self-correct (TR4/TR5)
- [x] `validate.py`: Pydantic structural + business rules; conflict + missing-info detection
- [x] `retry.py`: retryable(format) vs fail_fast(missing-info) classifier; capped retry-with-feedback
- [x] `calculated_total` vs `stated_total` → `conflict_detected` (computed, never trusted from model)
- [x] Validate: bad-sum flagged / clean not; format fixed on retry; missing-info fails fast (`test_validate`, `test_retry`)

## Phase 3 — Few-shot + variety (TR6)
- [x] `fewshot.py`: inline-citation paper, bibliography paper, tabular invoice examples
- [x] Wired into `prompts.build_messages` and both interactive + batch request builders
- [x] Validate: example turns present in the request; live layout behavior in integration tests

## Phase 4 — Batch + routing (TR7/TR8)
- [x] `batch.py`: submit/poll/reconcile by `custom_id`; resubmit only failures; chunk oversized
- [x] `confidence.py`: field-confidence + conflict/failure routing; threshold calibration
- [x] `audit.py`: per-type/per-field stratified accuracy
- [x] `data/corpus.py`: 13 labeled docs + seeded samples (bad-sum, absent-field, novel-category, format-error, missing-info)
- [x] Validate: reconcile by custom_id, resubmit only failures, low-confidence → review, per-type audit
      (`test_batch`, `test_confidence`, `test_audit`, `test_corpus`, `test_pipeline`)

## Verification
- [x] `pytest -m "not integration"` — 45 passed (offline regression gate green)
- [x] Integration tests collect + skip cleanly without a key (5 gated)
- [x] Import smoke; `run_example.py` degrades gracefully with no key
- [ ] Live: run `pytest -m integration` with a real key (extraction + ≥100-doc batch) — user's call (spends tokens)

## Review
- **What worked:** Pydantic-as-source-of-truth made the tool schema and validation impossible to
  drift; the extractor/validator injection in `retry.py` let both TR4 behaviors (format-fixed-on-retry
  and missing-info-fails-fast) be proven offline with scripted outputs. `reconcile()` as a pure
  function made the Batch `custom_id` recovery unit-testable with mocked out-of-order results.
- **Design calls:** `conflict_detected` is computed deterministically (not extracted) so the model's
  arithmetic judgment is never trusted — clean invoices are structurally guaranteed not to flag.
  `strict: true` was deliberately NOT used on tools: strict forbids Pydantic's constraints, and the
  whole point is loose syntactic guarantee + semantic Pydantic validation afterward.
- **Deferred to the user:** the live ≥100-doc batch (cost + up-to-24h window) is written as a faithful
  gated integration test but not executed here.
- **Could improve:** per-field (not just per-type) calibrated thresholds; stitching chunked-oversized-doc
  partial extractions back together; a reviewer UI for the flagged queue (stretch).
