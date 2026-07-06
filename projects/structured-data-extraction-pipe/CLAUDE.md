# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: greenfield (no code yet)

This project is **not started** — the directory holds only the spec (`docs/03-structured-data-extraction-pipeline.md`) and `.claude/commands/`, and is **entirely untracked** in the parent `claudemuse` monorepo (`git status` shows the whole dir as untracked; the commits in `git log` belong to sibling projects). Read the spec before writing anything: its functional requirements (**FR1–FR5**), technical requirements (**TR1–TR8**), and acceptance criteria are non-negotiable contracts, not suggestions.

The sibling projects `../customer-support/` and `../multi-agent-research-agent/` are complete, tested references for **house style and conventions** (repo layout, `pytest.ini`, `requirements.txt`, `run_example.py`, `_tasks/todo.md`, `.agents/plans/`) — consult their `CLAUDE.md` and `src/` before building. **But note the stack differs:** the siblings are built on the **Claude Agent SDK**; this project is a plain **`anthropic` SDK pipeline** — Messages API `tool_use` + the **Message Batches API** + **Pydantic**. Do not pull in `claude-agent-sdk` here.

## Environment

- Python **3.10** via the **shared virtualenv at the monorepo root**: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv` (this project has no venv of its own). Invoke `../../.venv/bin/python` or activate it.
- API keys live in the **monorepo-root `.env`** (`ANTHROPIC_API_KEY`) — two levels up from here. Load with `python-dotenv`.
- The stack is **not yet installed for this project** — add a `requirements.txt` (expect `anthropic`, `pydantic`, `pytest`, `python-dotenv`) and `pip install` into the shared venv when starting the build.
- Mirror the sibling `pytest.ini`: `testpaths = tests` and an `integration` marker for tests that make real API/Batch calls (so unit tests can run offline). Add `asyncio_mode = auto` only if you actually introduce async.
- Per global instructions: use `pytest`; check for an existing `tests/` dir before adding test files.

## The core design distinctions (what the exam probes — read first)

The whole point of this build is the line between **syntactic** and **semantic** correctness. `tool_use` + JSON Schema guarantees valid, well-typed JSON — it does **not** guarantee the values are right. Everything below exists because of that gap:

- **Schema is the contract (TR1).** Extraction happens through a `tool_use` call whose input schema is generated from a **Pydantic model** (single source of truth). Use `tool_choice: "any"` when the document type is unknown and multiple schemas compete; use **forced** `tool_choice` to guarantee a first step (e.g., `extract_metadata` before enrichment).
- **Resilient schema (TR2).** Maybe-absent fields are nullable (`["string","null"]`). Use an **extensible enum**: `"other"` + a detail string, plus `"unclear"` for ambiguity — so a novel category is captured, never dropped or errored. Enforces FR2 (**never fabricate** to satisfy a "required" field).
- **Normalization in the prompt (TR3).** Put normalization rules alongside the strict schema (dates → ISO 8601; "five bucks" → `{amount:5, currency:"USD"}`; "half" → `0.5`) to prevent valid-but-inconsistent values.
- **Validate + retry, and know the limit (TR4).** Validate with Pydantic (structural **and** business rules). On failure, retry with feedback: original document + failed extraction + the **specific** error. The critical distinction: **retry fixes format/structural errors; it does NOT recover absent information** ("Smith et al.", data in an unprovided doc) — those must **fail fast** and route to human review, not loop. Cap attempts.
- **Self-correction via arithmetic (TR5).** Extract a model-summed `calculated_total` alongside the page's `stated_total`, set `conflict_detected`, and flag for review **only when they differ** (clean invoices must not be flagged — FR3).
- **Few-shot for layout variety (TR6).** 2–4 examples spanning structures (inline citations vs bibliographies; narrative vs tables) to stop null/empty extraction on unfamiliar layouts.
- **Batch API for volume (TR7).** Use the **Message Batches API** (≈50% cheaper, ≤24 h window, **no multi-turn tool calling**). Correlate with `custom_id`; on failure resubmit **only** the failed docs (chunk oversized ones). Size the submission window to the SLA.
- **Confidence & human routing (TR8).** Emit field-level confidence, calibrate thresholds on a labeled set, route low-confidence/contradictory docs to humans and auto-accept the rest. **Audit accuracy stratified by document type and field** — an aggregate 97% can hide 40% errors for one type.

## Intended architecture (from the spec — no code exists yet)

- A small library of **extraction tools**, one Pydantic-derived schema per document type, plus a **router** that chooses `tool_choice: "any"` vs a forced tool.
- Pydantic models as the **single source of truth** — generate the JSON Schema from them; don't hand-write schemas that can drift from validation.
- A **validation-retry wrapper** that caps attempts and classifies each failure as **retryable (format)** vs **fail-fast (missing info)**.
- A **batch submitter** keyed by `custom_id` with per-doc failure recovery.
- A tiny **labeled validation set** (10–20 docs with known answers) to calibrate confidence thresholds and serve as accuracy ground truth, **segmented by type**.

## Validation is ground truth, not prose

Use the labeled set as ground truth and **assert on structure**, never on the model's wording: 100% schema-valid output across the set; missing fields return `null` (no fabrication); a novel category lands in `other`+detail; bad-sum invoices flagged via `calculated_total != stated_total` while clean ones are not; **both** a format-error-fixed-on-retry case and a missing-info-failed-fast case demonstrated; a ≥100-doc batch runs via the Batch API with seeded failures resubmitted by `custom_id`; accuracy reported **by type and field**. Treat the suite as a **regression gate** before any prompt or schema change.

## Build order (PIV phases)

1. **Schema extraction.** `tool_use` + JSON Schema with nullable/enum-other + normalization rules. *Validate:* absent fields → null; novel types → `other`+detail; output always validates.
2. **Validate + self-correct.** Pydantic validation, retry-with-feedback, calculated-vs-stated conflict flag. *Validate:* arithmetic conflicts flagged; format errors fixed on retry; missing-info cases fail fast.
3. **Few-shot + variety.** Add layout examples. *Validate:* fields in unusual layouts are now extracted.
4. **Batch + routing.** Batch API with `custom_id` recovery; confidence calibration + stratified audit. *Validate:* failed docs resubmitted; low-confidence routed to humans; per-type accuracy measured.

## Workflow

Slash commands under `.claude/commands/` drive a PIV loop: `core_piv_loop/prime` (understand the codebase), `core_piv_loop/plan-feature` (deep plan → written to `.agents/plans/{name}.md`), `core_piv_loop/execute` (implement a plan top-to-bottom, running its validation commands), `core_piv_loop/prime-tools`, plus `create-prd`, `first-ask-pre-plan`, and `commit`. Per global instructions, present a plan and get approval before non-trivial work; track it in `_tasks/todo.md`.
