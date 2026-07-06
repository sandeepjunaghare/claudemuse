# PRD — Structured Data Extraction Pipeline

> **Source of truth:** [`03-structured-data-extraction-pipeline.md`](./03-structured-data-extraction-pipeline.md). This PRD expands that spec into an implementation-ready document. Where the two diverge, the original spec's **FR1–FR5**, **TR1–TR8**, and acceptance criteria win.
>
> **Status:** Greenfield, spec-driven, no implementation yet · **Difficulty:** ●●○ · **Effort:** 2–3 days · maps to CCA-F **Exam Scenario 6** (D4 Prompt Engineering & Structured Output · D5 Context & Reliability).

---

## 1. Executive Summary

The Structured Data Extraction Pipeline turns messy, unstructured documents — invoices, contracts, research papers — into **schema-valid, semantically validated JSON at volume**. Extraction runs through the Claude Messages API's `tool_use` with a JSON Schema generated from a **Pydantic model**, which makes the *syntax* of the output a guarantee rather than a hope. On top of that guarantee sits the part that actually matters: **Pydantic validation, retry-with-feedback, arithmetic self-correction, and confidence-based human routing** — because a well-formed JSON object can still be *wrong*.

The product's reason for being is the single distinction the exam probes hardest: `tool_use` + JSON Schema eliminates **syntax** errors but not **semantic** ones. So the pipeline must do more than emit valid JSON — it must return `null` instead of fabricating an absent field, capture a novel category via an extensible enum instead of dropping the record, flag an invoice whose line items don't sum to its stated total, **retry format errors but fail fast on genuinely missing information**, and route only genuinely uncertain cases to a human while auto-accepting the rest. At volume, it uses the **Message Batches API** (≈50% cheaper) with `custom_id` correlation so a partial failure resubmits only the failed documents.

**MVP goal:** From a document, produce JSON that **always validates against its schema**, returns `null` for absent fields (**never fabricated**), captures novel categories via `other` + detail, **flags invoices whose `calculated_total ≠ stated_total`** while leaving clean ones untouched, demonstrates **both** a format-error-fixed-on-retry case **and** a missing-info-failed-fast case, runs a **≥100-document batch** via the Batch API with seeded failures resubmitted by `custom_id`, and reports **accuracy stratified by document type and field** — not just an aggregate.

## 2. Mission

**Mission:** Convert unstructured documents into JSON that is both syntactically guaranteed and semantically trustworthy — extracting what is present, refusing to invent what is absent, catching its own arithmetic, and escalating only the cases a human actually needs to see.

**Core principles:**

1. **Schema is the contract.** One Pydantic model per document type is the single source of truth; the JSON Schema handed to `tool_use` is generated from it, never hand-written to drift apart.
2. **Never fabricate.** A field genuinely absent from the source returns `null`. A novel category lands in `other` + detail. Missing information is a fact to report, not a gap to fill.
3. **Syntax is free; semantics are earned.** `tool_use` guarantees valid JSON. Validation, self-correction, and confidence exist because valid JSON can still be wrong.
4. **Retry what retry can fix.** Format/structural errors get a retry-with-feedback loop; absent information fails fast to human review — retrying it only burns tokens.
5. **Escalate by uncertainty, not by volume.** Field-level confidence and conflict flags route only genuinely uncertain or contradictory documents to humans; the rest auto-accept.
6. **Ground truth is a labeled set.** Success is measured against 10–20 known-answer documents, **segmented by type and field** — an aggregate 97% can hide 40% errors for one type.

## 3. Target Users

| Persona | Description | Technical comfort | Key needs / pain points |
|---|---|---|---|
| **Back-office operator** | Runs thousands of documents through the pipeline; owns throughput and cost. | Low–medium — configures a batch, reads a summary. | Volume at low cost, partial-failure recovery, a small trustworthy queue of exceptions rather than reviewing everything. |
| **Human reviewer** | Handles the documents the pipeline routes for review. | Medium. | Only genuinely uncertain/contradictory cases surfaced, with the specific reason (low confidence, sum conflict, missing info) attached. |
| **Builder / maintainer (you)** | Engineer building and regression-testing the pipeline. | Expert. | Pydantic-as-source-of-truth, a seeded labeled set that makes every failure mode reproducible, a suite that gates prompt/schema changes. |
| **Accuracy reviewer** | Audits extraction quality (and the exam grader). | High. | Per-type / per-field accuracy (not an aggregate), evidence that retry helps format errors but not missing info, calibrated confidence thresholds. |

## 4. MVP Scope

### In Scope ✅

**Core Functionality**
- ✅ Extract a defined field set from a document into JSON that **always validates** against a schema (FR1, TR1)
- ✅ Return `null` for genuinely absent fields; **never fabricate** to satisfy a "required" field (FR2, TR2)
- ✅ Capture a novel category via `other` + detail (and `unclear` for ambiguity) instead of dropping/erroring (TR2)
- ✅ Detect internal inconsistencies — line items not summing to the stated total — and flag them (FR3, TR5)
- ✅ Validate with Pydantic (structural **and** business rules); retry format errors with feedback, **fail fast** on missing info (FR1, TR4)
- ✅ Process large batches cost-effectively and recover from partial failures (FR4, TR7)
- ✅ Emit field-level confidence; route low-confidence/contradictory docs to review, auto-accept the rest (FR5, TR8)

**Technical**
- ✅ `tool_use` extraction with a **Pydantic-derived JSON Schema** as the contract (TR1)
- ✅ Router: `tool_choice: "any"` when document type is unknown across multiple schemas; **forced** `tool_choice` to guarantee a first step (e.g., `extract_metadata`) (TR1)
- ✅ Resilient schema: nullable fields (`["string","null"]`) + extensible enum (`other` + detail, `unclear`) (TR2)
- ✅ Normalization rules in the prompt alongside the strict schema (dates → ISO 8601; "five bucks" → `{amount:5, currency:"USD"}`; "half" → `0.5`) (TR3)
- ✅ Validation-retry wrapper that caps attempts and **classifies retryable (format) vs fail-fast (missing info)** (TR4)
- ✅ Self-correction: model-summed `calculated_total` alongside page `stated_total`, `conflict_detected` set **only when they differ** (TR5)
- ✅ Few-shot examples (2–4) spanning layouts — inline citations vs bibliographies, narrative vs tables (TR6)
- ✅ Message Batches API submission keyed by `custom_id`; resubmit **only** failed docs, chunk oversized ones (TR7)
- ✅ Confidence calibration on the labeled set + **stratified accuracy audit by type and field** (TR8)

**Integration**
- ✅ A small **labeled validation set** (10–20 docs, known answers, segmented by type) as ground truth
- ✅ Seeded sample documents engineered to trigger every behavior (bad-sum invoice, absent field, novel category, format-error, missing-info)
- ✅ Runnable entry point that takes a document and returns validated JSON + confidence + routing decision

### Out of Scope ❌

- ❌ OCR research or image/PDF ingestion — use provided text/sample documents (spec non-goal)
- ❌ A document-management UI or reviewer front-end (stretch: reviewer UI)
- ❌ Perfect accuracy or beating SOTA extraction quality
- ❌ A hosted FastAPI service / deployment infrastructure (stretch: FastAPI endpoint)
- ❌ An eval harness wired as a CI deploy gate (stretch)
- ❌ Multi-turn tool calling inside batch jobs (**not supported** by the Batch API — a constraint, not a choice)
- ❌ Authentication / multi-tenant access control

## 5. User Stories

1. **As a back-office operator,** I want every extraction to be schema-valid JSON, **so that** downstream systems never break on malformed output.
   - *Example:* 100% of outputs across the test set parse and validate — no syntax errors, ever.
2. **As an accuracy reviewer,** I want absent fields returned as `null` rather than guessed, **so that** the pipeline never quietly invents data.
   - *Example:* An invoice with no PO number returns `"po_number": null`, not a plausible-looking fabricated one.
3. **As a back-office operator,** I want a document of a category we've never seen to still be captured, **so that** new cases don't drop out of the pipeline.
   - *Example:* An unfamiliar document type lands as `{"category": "other", "category_detail": "..."}` instead of erroring or being discarded.
4. **As an accuracy reviewer,** I want invoices whose line items don't match the stated total flagged, **so that** arithmetic errors surface instead of being trusted.
   - *Example:* Line items sum to $980 but the invoice says $1,080 → `conflict_detected: true`, routed to review; a clean invoice is **not** flagged.
5. **As a human reviewer,** I want format errors fixed automatically but genuinely-missing info escalated, **so that** I only see cases a retry can't solve.
   - *Example:* A malformed date is fixed on retry-with-feedback; "author is 'Smith et al.', full list in an unprovided doc" **fails fast** to my queue.
6. **As a back-office operator,** I want to process thousands of documents cheaply and recover from partial failures, **so that** one bad document doesn't force a full re-run.
   - *Example:* A ≥100-doc batch runs via the Batch API; the ~3 seeded failures are resubmitted by `custom_id`, not the whole batch.
7. **As a human reviewer,** I want only low-confidence or contradictory documents routed to me, **so that** I'm not drowning in auto-acceptable cases.
   - *Example:* Confidence thresholds calibrated on the labeled set send ~5% to review; the rest auto-accept.
8. **As an accuracy reviewer,** I want accuracy reported by document type and field, **so that** a strong aggregate can't hide a weak segment.
   - *Example:* Overall 97%, but contracts' `effective_date` is 60% — the stratified report catches it; the aggregate would not.

## 6. Core Architecture & Patterns

**Extraction contract (TR1).** A document flows through a `tool_use` call whose input schema is generated from a Pydantic model. A **router** decides the tool-choice strategy: `tool_choice: "any"` when the type is unknown and multiple schemas compete, or a **forced** tool to guarantee a first step (e.g., `extract_metadata` → then enrich).

```
                                       ┌──────────────┐
   document ──▶ router (any vs forced) │  tool_use    │──▶ raw JSON (syntax guaranteed)
                                       │  extraction  │
                                       └──────────────┘
                                              │
                                              ▼
                     ┌─────────────── Pydantic validate ───────────────┐
                     │  structural  +  business rules  +  self-correct  │
                     └──────────────────────┬──────────────────────────┘
                        pass                 │ fail
                          │        ┌─────────┴──────────┐
                          │   retryable (format)?   fail-fast (missing info)?
                          │   → retry w/ feedback    → human review
                          ▼          (capped)
                 confidence + conflict routing
                   │                       │
              auto-accept            human review queue
```

**Proposed directory structure** (mirrors the sibling `multi-agent-research-agent` / `customer-support` projects):

```
src/
  schemas/             # Pydantic models = single source of truth (JSON Schema generated from these)
    invoice.py         #   nullable fields, extensible enum (other/unclear), calculated vs stated total
    contract.py
    paper.py
  extract.py           # tool_use extraction call + router (tool_choice: any vs forced)
  validate.py          # Pydantic structural + business-rule validation
  retry.py             # validation-retry loop; retryable (format) vs fail-fast (missing info) classifier
  confidence.py        # field-level confidence + calibrated routing thresholds
  batch.py             # Message Batches submitter + custom_id partial-failure recovery
  prompts.py           # system prompt: normalization rules + extraction instructions
  fewshot.py           # 2–4 layout examples for variety (TR6)
data/
  labeled/             # 10–20 known-answer docs (ground truth), segmented by type
  samples/             # seeded docs: bad-sum invoice, absent-field, novel category, format-error, missing-info
run_example.py         # single-document end-to-end entry point
audit.py               # stratified accuracy report by type + field
tests/                 # regression gate (schema validity, null-vs-fabrication, conflict, per-type accuracy)
```

**Key patterns:**
- **Pydantic as single source of truth.** Generate the JSON Schema from the model (`model_json_schema()`); validation and the extraction contract can never drift.
- **Resilient schema (TR2).** Maybe-absent fields typed `Optional`/nullable; categories as an extensible enum with `other` + detail and `unclear` — so novel inputs are captured, not dropped.
- **Normalization at the prompt layer (TR3).** Formatting rules (ISO dates, currency/amount parsing, fractions) live in the system prompt beside the strict schema to prevent valid-but-inconsistent values.
- **Retry classification (TR4).** The retry wrapper inspects the validation error: structural/format → retry-with-feedback (original doc + failed extraction + the *specific* error, capped attempts); absent information → fail fast to review. **Retrying missing info is the anti-pattern to avoid.**
- **Self-correction contract (TR5).** The schema carries both `calculated_total` (model-summed) and `stated_total`; a business rule sets `conflict_detected` only when they differ — clean docs are never flagged.
- **Batch correlation (TR7).** Each request carries a `custom_id`; the submitter reconciles results by `custom_id` and resubmits only failures (chunking oversized docs). No multi-turn tool calling inside a batch.
- **Confidence & stratified audit (TR8).** Field-level confidence thresholds calibrated on the labeled set; the audit reports accuracy per type and per field, never a lone aggregate.

**Model tiering:** extraction on a **Sonnet-tier** model (the accuracy/cost sweet spot for structured `tool_use`); trivial document-type routing on **Haiku-tier**; escalate the hardest layouts to **Opus-tier** only if calibration shows it pays. Use the latest models in each tier (Opus 4.8 / Sonnet 4.6 / Haiku 4.5). Confirm current model IDs and Batch behavior against the Claude API reference before wiring code.

## 7. Tools / Features

### 7.1 Extraction tools (schemas)

| Tool / schema | Purpose | Key fields | Resilience features |
|---|---|---|---|
| `extract_invoice` | Structured extraction from an invoice. | vendor, line items, `stated_total`, `calculated_total`, `conflict_detected`, dates, `po_number?` | Nullable optionals; `calculated_total` for self-correction; conflict flag (TR5). |
| `extract_contract` | Structured extraction from a contract. | parties, `effective_date`, term, `category` (enum + `other`/`unclear`) | Extensible enum for clause/type variety (TR2); ISO date normalization (TR3). |
| `extract_paper` | Structured extraction from a research paper. | title, authors, citations/references, sections | Handles inline-citation vs bibliography layouts via few-shot (TR6); `null` for absent authors, fail-fast on "et al." (TR4). |
| `extract_metadata` | Forced first step to identify document type/basics before enrichment. | doc_type, dates, language | Invoked via **forced** `tool_choice` to guarantee a first step (TR1). |

### 7.2 Router

- Picks **`tool_choice: "any"`** when the document type is unknown and multiple schemas compete, or a **forced** tool when a specific first step must be guaranteed. Single decision point; keeps the extraction contract explicit.

### 7.3 Validation-retry wrapper

- Runs Pydantic structural + business-rule validation. On failure, **classifies** the error and either retries with targeted feedback (capped) or fails fast to review. Emits a structured failure envelope (`type`, `retryable`, `detail`) for the reviewer queue.

### 7.4 Batch submitter

- Wraps the Message Batches API: builds requests with `custom_id`, submits within an SLA-sized window (≤24 h), polls, reconciles by `custom_id`, and resubmits only failures (chunking oversized docs).

### 7.5 Labeled validation set & audit

- 10–20 documents with known answers, **segmented by type**, seeded to include a bad-sum invoice, an absent field, a novel category, a format-error case, and a missing-info case. `audit.py` reports accuracy per type and field and calibrates confidence thresholds.

## 8. Technology Stack

- **Language:** Python **3.10** (shared monorepo venv at `../../.venv`).
- **Runtime:** the **`anthropic` SDK** — Messages API `tool_use` for extraction + the **Message Batches API** for volume. **Not** the Claude Agent SDK (unlike the sibling projects).
- **Validation:** **Pydantic** — models are the single source of truth; JSON Schema generated via `model_json_schema()`.
- **Models:** Sonnet-tier extraction, Haiku-tier routing, Opus-tier escalation if warranted (latest: Opus 4.8 / Sonnet 4.6 / Haiku 4.5).
- **Config:** `python-dotenv`; `ANTHROPIC_API_KEY` from the monorepo-root `.env`.
- **Testing:** `pytest`; mirror the sibling `pytest.ini` (`testpaths = tests`, an `integration` marker for tests that make real API/Batch calls so unit tests run offline). Add `asyncio_mode = auto` only if async is introduced.
- **Package management:** `pip` into the shared venv (add a `requirements.txt`: `anthropic`, `pydantic`, `pytest`, `python-dotenv`).
- **Optional / stretch:** `fastapi` + `uvicorn` for the endpoint; an eval-harness deploy gate; a reviewer UI.

## 9. Security & Configuration

- **Auth:** `anthropic` SDK uses `ANTHROPIC_API_KEY` from the root `.env`; no per-user auth in scope.
- **Configuration:** env-driven; retry caps, confidence thresholds, batch window, and model tiers as named constants.
- **Data handling:** documents may contain sensitive fields — keep sample/labeled docs synthetic; no secrets in code or committed data.
- **Security scope:** *In* — deterministic caps on retry attempts (runaway-loop backstop), synthetic test data, no fabricated values leaking downstream. *Out* — network hardening, PII redaction, multi-tenant isolation, deployment.

## 10. API Specification

Not a networked API for the MVP. The public surface is a single entry point (a FastAPI wrapper is a stretch goal):

```python
result = extract_document(document: str, doc_type: str | None = None) -> ExtractionResult
# ExtractionResult = {
#   "data": {...},                       # schema-valid JSON (null for absent fields)
#   "valid": bool,                       # passed Pydantic structural + business rules
#   "conflict_detected": bool,           # calculated_total != stated_total (TR5)
#   "confidence": {field: float},        # field-level confidence (TR8)
#   "route": "auto_accept" | "human_review",
#   "failure": {"type": str, "retryable": bool, "detail": str} | None,
# }

# Batch surface:
batch = submit_batch(documents: list[Document]) -> BatchHandle   # custom_id per doc
results = collect_batch(batch) -> {custom_id: ExtractionResult}  # resubmit only failures
```

- **Input:** raw document text (+ optional known type).
- **Output:** validated JSON with field-level confidence, conflict flag, routing decision, and a structured failure envelope when it fails fast.

## 11. Success Criteria

**MVP is successful when** documents become schema-valid JSON that refuses to fabricate, catches its own arithmetic, retries what retry can fix, escalates the rest, and scales via the Batch API. Validation asserts on **structure and the labeled set**, never on prose.

- ✅ **100% of outputs are schema-valid JSON** (no syntax errors) across the test set.
- ✅ Documents missing a field return **`null`, not a fabricated value**.
- ✅ A novel category is captured via **`other` + detail** rather than dropped or errored.
- ✅ Invoices with bad sums are flagged via **`calculated_total != stated_total`**; clean ones are not.
- ✅ **Both** demonstrated: retry fixes a format error, **and** a missing-info case fails fast to human review.
- ✅ A batch of **≥100 docs** runs via the Batch API; the ~3 seeded failures are **resubmitted by `custom_id`**.
- ✅ Accuracy reported **by document type and field**, not just an aggregate.

**Quality indicators:** confidence thresholds calibrated on the labeled set route only genuinely uncertain docs; a format error is fixed within the retry cap; a clean invoice is never flagged; the suite gates every prompt/schema change (regression gate).

## 12. Implementation Phases (PIV)

### Phase 1 — Schema Extraction
- **Goal:** `tool_use` + Pydantic-derived JSON Schema with nullable/enum-other + normalization rules.
- **Deliverables:** ✅ `requirements.txt` + `anthropic`/`pydantic` installed · ✅ Pydantic models (invoice/contract/paper) → generated JSON Schema · ✅ `extract.py` with router (`any` vs forced `tool_choice`) · ✅ normalization rules in `prompts.py` · ✅ `run_example.py`.
- **Validate:** absent fields return `null`; novel types land in `other` + detail; output **always** validates.

### Phase 2 — Validate + Self-Correct
- **Goal:** Pydantic validation, retry-with-feedback, calculated-vs-stated conflict flag.
- **Deliverables:** ✅ `validate.py` (structural + business rules) · ✅ `retry.py` with retryable-vs-fail-fast classifier + capped attempts · ✅ `calculated_total`/`stated_total`/`conflict_detected` contract.
- **Validate:** arithmetic conflicts flagged (clean ones not); a format error is fixed on retry; a missing-info case fails fast.

### Phase 3 — Few-Shot + Variety
- **Goal:** Fix null/empty extraction on unfamiliar layouts.
- **Deliverables:** ✅ `fewshot.py` with 2–4 examples spanning layouts (inline citations vs bibliographies; narrative vs tables).
- **Validate:** fields present in unusual layouts are now extracted (were previously null/empty).

### Phase 4 — Batch + Routing
- **Goal:** Batch API with `custom_id` recovery; confidence calibration + stratified audit.
- **Deliverables:** ✅ `batch.py` (submit/poll/reconcile by `custom_id`, resubmit failures, chunk oversized) · ✅ `confidence.py` thresholds calibrated on the labeled set · ✅ `audit.py` per-type/per-field accuracy.
- **Validate:** ≥100-doc batch runs; ~3 seeded failures resubmitted by `custom_id`; low-confidence routed to humans; per-type accuracy measured.

## 13. Future Considerations

- A **FastAPI endpoint** accepting a document and returning validated JSON + confidence.
- An **eval harness** wired as a deploy gate that scores extraction accuracy before shipping a prompt/schema change.
- A **reviewer UI** surfacing only flagged / low-confidence documents with the escalation reason attached.
- Real **document ingestion** (PDF/image → text) upstream of extraction (explicitly out of MVP scope).
- **Active-learning loop:** reviewer corrections feed back into the few-shot bank and threshold calibration.

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Fabrication under "required"** — model invents a value to fill a required field. | Silent bad data downstream; the cardinal failure. | Nullable schema + explicit "return null, never fabricate" prompt rule (TR2); labeled-set test asserts `null` on absent fields. |
| **Retrying the unfixable** — looping on genuinely-missing info. | Wasted tokens/latency; a case that never resolves. | Retry wrapper **classifies** format (retry) vs missing-info (fail-fast); capped attempts; missing-info routes to review (TR4). |
| **Semantic-but-valid errors** — JSON validates yet values are wrong (e.g., bad sum). | False confidence; undetected arithmetic errors. | Self-correction contract (`calculated_total` vs `stated_total` → `conflict_detected`) + business-rule validation (TR5). |
| **Aggregate hides a weak segment** — 97% overall masks 40% for one type. | Ships a type that's quietly broken. | Stratified audit by type **and** field on the labeled set; calibrate thresholds per segment (TR8). |
| **Batch partial failure** — one bad doc forces a full re-run, or failures are lost. | Cost blow-up or silent data loss. | `custom_id` correlation; resubmit **only** failures; chunk oversized docs (TR7). |
| **Layout variety breaks extraction** — unfamiliar structures yield null/empty. | Whole documents extract poorly. | 2–4 few-shot examples spanning layouts (TR6); labeled set includes unusual layouts as regression cases. |

## 15. Appendix

**Related documents**
- Spec (source of truth): [`03-structured-data-extraction-pipeline.md`](./03-structured-data-extraction-pipeline.md)
- Sibling reference implementations: `../../multi-agent-research-agent/`, `../../customer-support/` (house style: repo layout, `pytest.ini`, `run_example.py`, `_tasks/todo.md`, `.agents/plans/`)
- Project guidance: [`../CLAUDE.md`](../CLAUDE.md)

**Read first (from the spec)**
- [Tool use](https://platform.claude.com/docs/en/build-with-claude/tool-use)
- [Message Batches](https://platform.claude.com/docs/en/build-with-claude/message-batches)
- Prompt Engineering [overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)

**CCA-F coverage**

| Task statement | Exercised by |
|---|---|
| D4.2 Few-shot prompting | TR6 |
| D4.3 Structured output via tool_use / schema design | TR1, TR2, TR3 |
| D4.4 Validation, retry, self-correction | TR4, TR5 |
| D4.5 Batch processing | TR7 |
| D5.5 Confidence calibration & human review | TR8 |
