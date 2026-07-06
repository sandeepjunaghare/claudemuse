# Project 03 — Structured Data Extraction Pipeline

> **Pitch:** Turn messy documents (invoices, contracts, papers) into validated, schema-correct JSON at
> volume — with nullable fields, self-correction, retry-with-feedback, batch processing, and human-review
> routing.
> **Primary domains:** D4 Prompt Engineering & Structured Output · D5 Context & Reliability.
> **Difficulty:** ●●○ · **Effort:** 2–3 days · maps to **official Exam Scenario 6**.

## Problem statement

A back office processes thousands of unstructured documents. You build an extraction pipeline that produces
**syntactically guaranteed** and **semantically validated** JSON, handles edge cases (missing fields, varied
layouts, conflicting totals) without fabricating data, scales cost-effectively, and routes only genuinely
uncertain cases to humans.

## Background / why it matters

This is the structured-output and reliability core of the exam. The distinction that matters: `tool_use` +
JSON Schema eliminates *syntax* errors but not *semantic* ones — so you also need validation, self-correction,
and a clear-eyed sense of when retry helps (format errors) vs when to fail fast (information absent from source).

## Goals & non-goals

- **Goals:** schema-constrained extraction; nullable/enum-other design; validation-retry loops; self-correction
  for arithmetic; few-shot for layout variety; Batch API for volume; confidence-based human routing.
- **Non-goals:** OCR research, a document-management UI, or perfect accuracy. Use provided/sample documents.

## Functional requirements

- FR1. Extract a defined field set from a document into JSON that always validates against a schema.
- FR2. Return `null` for fields genuinely absent; never fabricate to satisfy a "required" field.
- FR3. Detect internal inconsistencies (e.g., line items not summing to the stated total) and flag them.
- FR4. Process large batches cost-effectively and recover from partial failures.
- FR5. Route low-confidence or contradictory extractions to human review; auto-accept the rest.

## Technical requirements (mapped to CCA-F task statements)

- **TR1 — Structured output (D4.3).** Use `tool_use` with a JSON Schema as the extraction contract — guarantees
  valid, well-typed JSON. Use `tool_choice: "any"` when the document type is unknown and multiple schemas
  exist; use **forced** `tool_choice` to guarantee a first step (e.g., `extract_metadata` before enrichment).
- **TR2 — Resilient schema (D4.3).** Mark maybe-absent fields nullable (`["string","null"]`). Use an extensible
  enum: add `"other"` + a detail string and `"unclear"` for ambiguous cases (resilient catch-all), so new
  categories don't drop records.
- **TR3 — Format normalization (D4.3).** Put normalization rules in the prompt alongside the strict schema
  (dates → ISO 8601; "five bucks" → {amount:5, currency:"USD"}; "half" → 0.5) to prevent
  valid-but-inconsistent values.
- **TR4 — Validation & retry (D4.4).** Validate with Pydantic (structural + business rules). On failure, retry
  with feedback: include the original document, the failed extraction, and the **specific** error. **Recognize
  the limit:** retry fixes format/structural errors but **not** absent information ("Smith et al.", data in an
  unprovided doc) — fail fast and route those to human review.
- **TR5 — Self-correction (D4.4).** Extract a model-summed `calculated_total` alongside the page's
  `stated_total`, set `conflict_detected`, and flag for human review **only when they differ**.
- **TR6 — Few-shot for variety (D4.2).** Add 2–4 examples covering varied structures (inline citations vs
  bibliographies; narrative vs tables) to fix null/empty extraction on unfamiliar layouts.
- **TR7 — Batch processing (D4.5).** Use the Message Batches API for volume (≈50% cheaper, ≤24 h window, no
  multi-turn tool calling). Correlate with `custom_id`; on failure, resubmit **only** failed docs (chunking
  oversized ones). Size the submission window to your SLA (e.g., ≤6 h slack for a 30-h deadline).
- **TR8 — Confidence & human routing (D5.5).** Output field-level confidence; calibrate thresholds on a labeled
  set; route low-confidence/contradictory docs to humans. Audit accuracy by **document type and field**
  (stratified sampling) — an aggregate 97% can hide 40% errors for one type.

## Architecture guidance (references, not code)

- A small library of extraction tools (one schema per document type) + a router that picks `any` vs a forced
  tool. Pydantic models as the single source of truth (generate JSON Schema from them). A validation-retry
  wrapper that caps attempts and classifies "retryable vs fail-fast." A batch submitter keyed by `custom_id`.
- Build a tiny labeled validation set (10–20 docs with known answers) to calibrate confidence thresholds and to
  serve as your accuracy ground truth, segmented by type.

## Build phases (PIV)

1. **Schema extraction.** `tool_use` + JSON Schema with nullable/enum-other + normalization rules. *Validate:*
   absent fields return null; novel types land in `other`+detail; output always validates.
2. **Validate + self-correct.** Pydantic validation, retry-with-feedback, calculated-vs-stated conflict flag.
   *Validate:* arithmetic conflicts flagged; format errors fixed on retry; missing-info cases fail fast.
3. **Few-shot + variety.** Add layout examples. *Validate:* fields present in unusual layouts are now extracted.
4. **Batch + routing.** Batch API with custom_id recovery; confidence calibration + stratified audit.
   *Validate:* failed docs resubmitted correctly; low-confidence routed to humans; per-type accuracy measured.

## Acceptance criteria

- [ ] 100% of outputs are schema-valid JSON (no syntax errors) across the test set.
- [ ] Documents missing a field return `null`, not a fabricated value.
- [ ] A novel category is captured via `other` + detail rather than dropped or erroring.
- [ ] Invoices with bad sums are flagged via `calculated_total != stated_total`; clean ones are not.
- [ ] Retry fixes a format error; a "missing info" case is failed fast to human review (both demonstrated).
- [ ] A batch of ≥100 docs runs via the Batch API; the ~3 seeded failures are resubmitted by `custom_id`.
- [ ] Accuracy reported **by document type and field**, not just an aggregate.

## Validation strategy

Use the labeled set as ground truth; assert schema validity, null-vs-fabrication behavior, conflict detection,
and per-segment accuracy. Treat the suite as a regression gate before any prompt/schema change.

## Stretch goals

- A FastAPI endpoint that accepts a document and returns validated JSON + confidence. · An eval harness that
  scores extraction accuracy as a deploy gate. · A reviewer UI that surfaces only flagged/low-confidence docs.

## CCA-F coverage

| Task statement | Exercised by |
|---|---|
| D4.2 Few-shot prompting | TR6 |
| D4.3 Structured output via tool_use / schema design | TR1, TR2, TR3 |
| D4.4 Validation, retry, self-correction | TR4, TR5 |
| D4.5 Batch processing | TR7 |
| D5.5 Confidence calibration & human review | TR8 |

**Read first:** [Tool use](https://platform.claude.com/docs/en/build-with-claude/tool-use);
[Message Batches](https://platform.claude.com/docs/en/build-with-claude/message-batches);
Prompt Engineering [overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview).
