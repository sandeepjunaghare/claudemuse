# Feature: Phase 4 — Reliability + Provenance (TR7, TR8, TR9)

The following plan should be complete, but it is important that you **validate documentation and
codebase patterns and task sanity before you start implementing.**

Pay special attention to naming of existing utils, types, and models. This project uses **flat
absolute imports** off `src/` (`import config`, `from loop import run_turn`, `from mocks import
corpus`), wired by `tests/conftest.py`. Do NOT introduce package-relative imports. The codebase is
uniformly Python **snake_case** — the global camelCase preference yields to the project convention.
Reuse existing names verbatim: `AgentRun`, `run_turn`, `run_research`, `_run_with_refinement`,
`build_*_options`, `format_search`, `coverage_eval.evaluate`, `corpus.FACETS`, `schemas.Claim`,
`schemas.SourceRef`, `schemas.Report`, `config.MAX_REFINEMENT_ITERATIONS`.

> **Confirmed design decisions (locked with the user before planning):**
> 1. **Timeout granularity = single-source gap.** The D004 endpoint (Recording Artists Coalition)
>    is unreachable; the **music facet stays `covered` via D003**; the report **annotates the one
>    missing source**. This keeps TR7 partial-results cleanly separate from TR4/TR5 facet coverage
>    (it does NOT create a facet gap and does NOT fight the refinement loop).
> 2. **Retry placement = subagent-prompt-driven.** The tool returns a **deterministic structured
>    error envelope** (unit-tested as a pure function); the subagent prompt instructs 1–2 retries on
>    a *retryable* error, then return a structured failure. The access-failure-vs-valid-empty
>    distinction is deterministic/unit-tested; the retry-*attempt* itself is model-driven and is
>    validated by asserting the prompt contract + graceful live degradation (not by counting a
>    subagent's isolated tool calls, which the loop cannot see — TR6).
> 3. **Provenance format = machine-readable `CLAIMS:` block.** The coordinator emits a structured
>    `CLAIMS:` block (mirrors the Phase-3 `COVERAGE:` block); a **pure parser** (`provenance.py`)
>    builds `schemas.Report.claims` as `Claim` + `SourceRef`. **FR5 (100% of claims cited)** is
>    asserted on parsed claims, deterministically.
>
> Additional locked assumptions: synthesis + TR9 rendering stay **coordinator-owned** (no new
> `synthesis`/`report` subagents, honoring the Phase-1 decision); conflict/temporal handling is
> **prompt-driven** and asserted on structure; `run_research` keeps returning `AgentRun` with a new
> `.report: Report` attached (same pattern as `.route`/`.coverage`); the `CLAIMS:` parser lives in a
> new single-purpose `src/provenance.py`.

---

## Feature Description

Phases 1–3 built the hub-and-spoke spine, parallel fan-out + dynamic triage, and coverage
verification + a bounded refinement loop. Throughout, the seeded corpus's *failure-mode* data has
been **inert**: the D004 `timeout: True` marker is ignored, the D007/D008 conflict pair (40% @ 2023
vs 55% @ 2025) is retrieved as ordinary text, and `schemas.Report.claims` / `.coverage` have never
been assembled from a real run. Phase 4 turns all of that into behavior, delivering the four
capabilities that justify the ~15× multi-agent cost against a single-agent chat:

1. **Structured error propagation (TR7):** `web_search` gains a structured **error envelope**
   (failure type, `is_retryable`, attempted query echoed, partial results, alternatives). An
   **access failure** (the timed-out endpoint) is distinguished from a **valid empty result** (the
   corpus genuinely has no such source). Subagents retry 1–2× locally on a retryable error, then
   propagate a structured failure — the run **never aborts** and **never silently swallows** a gap.
2. **Provenance (TR8):** every claim carries claim → source → excerpt → **date**, preserved through
   synthesis into a `schemas.Report`. FR5 ("100% of claims carry a source") becomes a real,
   deterministic test on parsed claims.
3. **Conflict + temporal handling (TR8):** the D007/D008 film pair both appear with attribution and
   dates, the temporal difference noted — never silently resolved to one value.
4. **Coverage annotations by content type (TR9):** quantitative figures render as a **table**,
   qualitative analysis as **prose**, and a **"Coverage & Gaps"** section marks well-supported
   facets vs. areas limited by unavailable sources (the RAC timeout lands here).

Consistent with the house ethos, every hard property is validated on **structure** — parsed claims,
the error-envelope shape, coverage annotations, presence of both conflicting sources — never on the
model's prose.

## User Story

As a **downstream reader** of the briefing,
I want **every claim traceable to a dated source, conflicting sources shown side by side, and a
usable report even when one source is unavailable**,
So that **I can trust and act on the briefing — no orphan facts, no hidden disagreements, and one
failed source never sinks the whole report.**

Supporting PRD stories (§5): #3 (every claim carries source + date), #4 (conflicting sources shown
side by side with dates), #5 (a usable report when a source is unavailable, gap annotated).

## Problem Statement

- **Swallowed errors (Risk table, PRD §14):** the D004 timeout marker is inert. Today a subagent has
  no structured way to say "this endpoint failed but here are partial results" vs. "the corpus has
  nothing" — the two collapse into the same empty string. TR7 is unmet.
- **Lost provenance:** `schemas.Report.claims` has been stubbed since Phase 1 with **no producer**.
  There is no deterministic proof that 100% of the report's claims carry a source (FR5) — the
  acceptance criterion is unverified.
- **Conflicts risk silent resolution:** nothing in the contract forces the D007/D008 pair to both
  survive synthesis with their dates; the model could pick one value (TR8 unmet as a *contract*).
- **No content-type rendering:** TR9 (tables for figures, prose for analysis, gap annotations) has
  no prompt contract and no structural check.

## Solution Statement

- **`src/errors.py` (new, pure, SDK-free):** failure-type constants + `is_retryable()` classifier +
  an `ErrorEnvelope` dataclass with a text renderer. This is the single source of truth for the
  access-failure-vs-valid-empty distinction.
- **`tools/server.py` `format_search` (extend):** partition matched docs into *available* vs.
  *timed-out* (reads `doc.get("timeout")`, leaving `mocks/corpus.py` data-only). Render three
  outcomes: **clean** (existing), **valid empty** (existing), and **timeout** — either **partial**
  (available hits + an `ERROR:` block naming the unavailable source, retryable) when other sources
  exist, or a **full access failure** (no content, retryable) when the *only* match is the timed-out
  doc (the by-reference fetch of D004). Shared by both server flavors (external stdio + in-process).
- **`src/provenance.py` (new, pure, SDK-free):** `parse_claims_block(text) -> list[Claim]` and
  `build_report(text, coverage, gaps) -> Report`. Parses the coordinator's `CLAIMS:` block into
  `Claim` + `SourceRef`, mirroring `coverage_eval.parse_coverage_block`.
- **`coordinator.py` `SYSTEM_PROMPT` (extend):** add the `CLAIMS:` block contract, the
  conflict/temporal contract, the source-unavailable handling rule (keep the facet covered if other
  evidence exists; annotate the unavailable source — do NOT downgrade the facet to a gap), and the
  TR9 rendering contract (figures → table, analysis → prose, a "Coverage & Gaps" section).
- **Subagent prompts (extend):** `doc_analysis` + `web_search` get the retry-then-structured-failure
  contract for retryable access errors, and the partial-results usage rule.
- **`loop.py` `AgentRun` (extend):** add `report: Optional[schemas.Report] = None`.
- **`coordinator.run_research` (extend):** after the fan-out/refinement path, assemble
  `provenance.build_report(...)` and attach `run.report`. Single-agent path attaches a
  best-effort report if a claims block is present, else leaves `None`.
- **`config.py` (extend):** `MAX_TOOL_RETRIES = 2` (single source of truth for the subagent retry
  budget referenced in prompts; precedent: `MAX_REFINEMENT_ITERATIONS`).
- **`run_example.py` (extend):** print claims count + `all_claims_have_source()` + a note on the
  unavailable source.
- **Tests:** new `test_errors.py`, `test_provenance.py`; extend `test_tools_web_search.py`,
  `test_coordinator_config.py`; new integration `test_phase4_reliability_live.py`.

## Feature Metadata

**Feature Type:** New Capability (final PIV phase)
**Estimated Complexity:** Medium–High (no new SDK mechanic — like Phase 3, it is pure Python +
prompt contracts — but it touches the tool layer, adds two pure modules, changes retrieval behavior
that ripples into existing live tests, and adds four intertwined report contracts).
**Primary Systems Affected:** `tools/server.py`, `coordinator.py` (prompts + `run_research`),
`loop.py` (`AgentRun`), new `errors.py` + `provenance.py`, `config.py`, `run_example.py`, tests.
**Dependencies:** No new external libraries. Existing: `claude-agent-sdk`, `pytest`,
`pytest-asyncio`, `python-dotenv`, `mcp.server.fastmcp`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: READ THESE BEFORE IMPLEMENTING

- `docs/02-multi-agent-research-system.md` — the **source of truth**. TR7/TR8/TR9 wording is the
  non-negotiable contract; where it and the PRD diverge, the spec wins.
- `docs/02-multi-agent-research-prd.md` (§4 In-Scope Technical, §6 patterns, §7 tools/subagents,
  §11 Success Criteria, §12 Phase 4, §14 Risks) — Why: the deliverable checklist + acceptance.
- `src/schemas.py` (whole file, esp. `SourceRef` L19-29, `Claim` L31-37, `Report` L54-68,
  `all_claims_have_source` L64-68) — Why: the provenance types are **already defined and staged**;
  Phase 4 *populates* them, does not reshape them. `SourceRef.url` is `str | None` (optional).
- `src/coverage_eval.py` (whole file) — Why: the **exact pattern to mirror** for the `CLAIMS:`
  parser — a pure, SDK-free, total, never-raising block parser (`parse_coverage_block` L86-112,
  `evaluate` L115-135) with string status constants and a dataclass result. `provenance.py` should
  read like its sibling.
- `src/tools/server.py` (whole file, esp. `_WEB_SEARCH_DESCRIPTION` L38-52, `_format_hit` L55-58,
  `format_search` L61-75, the two server flavors L78-122) — Why: `format_search` is the pure
  function to extend; both flavors call it, so the envelope lands in **both** paths. Provenance is
  encoded in **TEXT** (`structuredContent` is dropped before the model sees it — L15-17).
- `src/coordinator.py` (whole file, esp. `SYSTEM_PROMPT` L70-121, `_PARTIAL_SYSTEM_PROMPT` L186-216,
  `_build_refinement_prompt` L327-353, `_run_with_refinement` L356-387, `run_research` L390-405) —
  Why: the prompt to extend + where to attach `run.report`. Note the `COVERAGE:` contract is already
  at the tail of `SYSTEM_PROMPT`; the `CLAIMS:` block goes alongside it.
- `src/loop.py` (`AgentRun` L89-185, esp. the post-hoc fields `route`/`coverage`/`gaps` L103-109) —
  Why: the pattern for a field set *after* the turn by `run_research`; add `report` the same way.
- `src/mocks/corpus.py` (D003 L59-67, D004 L68-81 with `timeout: True`, D007/D008 conflict pair
  L108-134, `search` L146-167) — Why: D004 is the timeout endpoint; D003 keeps music covered; the
  conflict pair's exact source names + dates are the live-assertion targets. `search` already
  returns D004 among music matches, so the timeout partitioning must happen in `format_search`.
- `src/triage.py` (L104-127) — Why: `run_research` routes here; unchanged in Phase 4 but the
  fan-out route is the one that gets a `report`.
- `src/config.py` (L37-46) — Why: where `MAX_TOOL_RETRIES` goes (mirror `MAX_REFINEMENT_ITERATIONS`
  L41 style — a named constant with a doc comment).
- `tests/conftest.py` (whole file) — Why: import strategy + the `run_research` /
  `run_partial_then_refine` fixtures; add a fixture only if a new live driver is needed.
- `tests/test_coverage.py` (whole file) — Why: the **template** for `test_provenance.py` — a
  deterministic unit table over a pure parser.
- `tests/test_tools_web_search.py` (whole file) — Why: extend it; shows the `format_search` unit
  style (assert on returned text substrings).
- `tests/test_coordinator_config.py` (L91-95 `test_system_prompt_carries_coverage_and_partitioning_contract`)
  — Why: the pattern for asserting a prompt-contract string is present.
- `tests/test_phase3_coverage_live.py` (whole file) — Why: the **template** for
  `test_phase4_reliability_live.py` — `pytestmark` skip guard, structure-only assertions,
  `run_research` fixture, lenient keyword checks.
- `tests/test_schemas.py` (whole file) — Why: confirms the `Report`/`Claim`/`SourceRef` invariants
  the parser must satisfy (esp. `all_claims_have_source`).
- `_tasks/todo.md` (Phase 1–3 reviews) — Why: house conventions for the todo checklist + review
  section you must append at the end.

### New Files to Create

- `src/errors.py` — failure-type constants, `is_retryable()`, `ErrorEnvelope` dataclass + text
  renderer. Pure, SDK-free (mirrors `coverage_eval.py` / `triage.py`).
- `src/provenance.py` — `parse_claims_block()` + `build_report()`. Pure, SDK-free; imports
  `schemas` only.
- `tests/test_errors.py` — deterministic unit table for `errors.py`.
- `tests/test_provenance.py` — deterministic unit table for the `CLAIMS:` parser + FR5 invariant.
- `tests/test_phase4_reliability_live.py` — the Phase-4 integration/acceptance demo (one broad
  coordinator run asserts timeout-degradation + provenance/FR5 + conflict + TR9).

### Relevant Documentation — READ BEFORE IMPLEMENTING

- Spec `docs/02-multi-agent-research-system.md`, TR7/TR8/TR9 (verbatim):
  - **TR7** — "A failing subagent returns failure type, attempted query, partial results, and
    alternatives. Distinguish an **access failure** (retry decision) from a **valid empty result**.
    Local recovery (1–2 retries) before propagating; never abort the whole run or silently suppress."
  - **TR8** — "Subagents output structured claim→source mappings (claim, source URL/name, excerpt,
    **publication date**). Synthesis preserves and merges them. Handle conflicting credible sources
    by annotating both with attribution; include dates so temporal differences aren't misread as
    contradictions."
  - **TR9** — "The report marks which findings are well-supported vs which areas have gaps due to
    unavailable sources. Render by content type (tables for figures, prose for analysis)."
- Agent SDK — [Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents): confirms
  subagent tool-call loops are internal (the coordinator/loop cannot intercept a subagent's
  individual tool call → retry must be prompt-driven, "local" to the subagent).
- Memory `mar-agent-sdk-delegation`: external stdio for coordinator/subagents; in-process for the
  single-agent fallback; both share `format_search`, so the envelope reaches both — verify still
  true before editing.
- **`claude-api` skill** — load it before touching model IDs or prompts (the repo names
  `claude-opus-4-8` / `claude-sonnet-4-6` / `claude-haiku-4-5-*`); do not change tiers.

### Patterns to Follow

**Pure-module pattern (mirror `coverage_eval.py` / `triage.py`):** SDK-free, stdlib-only, module
docstring stating "pure, total, deterministic, never raises," string constants for enums, a
`@dataclass` result, first-match-wins ordered lookups. This keeps the unit suite credential-free.

**Block-parser pattern (mirror `coverage_eval.parse_coverage_block` L86-112):** find a header line
(case-insensitive, stripped), consume `- <...>` lines until a blank/non-matching line, tolerate
malformed lines by skipping (never raise), return a plain structure. `parse_claims_block` follows
this exactly, but each line yields a `Claim(text, SourceRef(...))`.

**Provenance-in-text (server docstring L15-17, `_format_hit` L55-58):** the operative surface the
model sees is TEXT. The `ERROR:` envelope must be encoded in the returned text (like the existing
`[source, date]` citation shape), NOT only in `structuredContent`.

**Post-hoc `AgentRun` field (loop L103-109, `run_research` L398-405):** `route`/`coverage`/`gaps`
are dataclass fields with defaults, set by `run_research`/`_run_with_refinement` after the turn.
`report` follows the identical pattern.

**Prompt-contract test (test_coordinator_config L91-95):** assert the contract keyword is present in
the prompt string (`"CLAIMS:" in SYSTEM_PROMPT`), not the model's output.

**Live-test structure-only (test_phase3_coverage_live):** `pytestmark` with `integration` + a skip
guard on `shutil.which("claude") or config.anthropic_key_present()`; assert on parsed structure and
lenient keyword presence, never exact prose; include a slice of `final_text` in the assert message
for debugging.

**Machine-readable claim line shape (already emitted by subagents!):** `web_search.py` L38-40 and
`doc_analysis.py` L37-39 already instruct subagents to emit
`- <claim text> [source: <source name>, date: <YYYY-MM-DD>, url: <url>]`. The coordinator's
`CLAIMS:` block should aggregate these into the **same line shape**, so `parse_claims_block` parses
one consistent format.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (pure modules + config)

Build the SDK-free primitives first so they are fully unit-tested before any wiring or API call.

**Tasks:**
- `src/errors.py`: failure-type constants, `is_retryable()`, `ErrorEnvelope` dataclass + renderer.
- `src/config.py`: add `MAX_TOOL_RETRIES = 2`.
- `src/provenance.py`: `parse_claims_block()` + `build_report()`.
- Unit tests for both (`test_errors.py`, `test_provenance.py`) — green + fast before proceeding.

### Phase 2: Core Implementation (tool envelope + prompt contracts)

**Tasks:**
- `tools/server.py`: extend `format_search` with timeout partitioning → clean / valid-empty /
  partial / full-access-failure, using `errors.py`. Extend `_WEB_SEARCH_DESCRIPTION` to document the
  error/partial return.
- `coordinator.py` `SYSTEM_PROMPT`: add CLAIMS block + conflict/temporal + source-unavailable +
  TR9-rendering contracts.
- `agents/doc_analysis.py` + `agents/web_search.py`: add retry-then-structured-failure + partial-use
  contracts.

### Phase 3: Integration (assemble + attach the Report)

**Tasks:**
- `loop.py`: add `AgentRun.report` field (import `schemas`).
- `coordinator.run_research`: assemble + attach `run.report` on both routes.
- `run_example.py`: print provenance/FR5 line + unavailable-source note.

### Phase 4: Testing & Validation

**Tasks:**
- Extend `test_tools_web_search.py` (envelope cases) + `test_coordinator_config.py` (prompt
  contracts).
- New `test_phase4_reliability_live.py` (one broad run → four assertions).
- Full `pytest -m "not integration"` green; then full `pytest -m integration` (Phase 1–4) — the
  timeout activation changes retrieval behavior, so a **full live regression is required** this
  phase (do not defer it — see Risks).

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task is atomic and independently testable. The venv python is
`../../.venv/bin/python` (run all commands from the project root
`projects/multi-agent-research-agent/`).

### 1. CREATE `src/errors.py`

- **IMPLEMENT:** Pure, SDK-free module. Failure-type string constants:
  `FAILURE_ACCESS_TIMEOUT = "access_timeout"`, `FAILURE_VALID_EMPTY = "valid_empty"` (and a generic
  `FAILURE_ACCESS = "access_failure"` for future non-timeout access errors). A `_RETRYABLE` set
  containing the access failures (timeout, access) but **NOT** `valid_empty`. `is_retryable(failure_type: str) -> bool`
  returns membership (total; unknown type → False). An `ErrorEnvelope` dataclass:
  `type: str`, `attempted_query: str`, `is_retryable: bool`, `failed_source: str | None = None`,
  `partial: list[str] = field(default_factory=list)` (rendered partial-result lines),
  `alternative: str = ""`. A `render(self) -> str` method (or module `render_envelope(env)`) that
  emits a machine-readable `ERROR:` block in the same `- key: value` line style as the `COVERAGE:`
  block, e.g.:
  ```
  ERROR:
  - type: access_timeout
  - retryable: true
  - attempted_query: "AI music"
  - failed_source: Recording Artists Coalition
  - alternative: report this source as unavailable; other sources for this facet remain valid.
  ```
- **PATTERN:** `src/coverage_eval.py` L28-49 (dataclass + string constants + module docstring) and
  `src/triage.py` L32-34 (route string constants).
- **IMPORTS:** `from dataclasses import dataclass, field`. No SDK, no corpus import.
- **GOTCHA:** Keep it SDK-free and corpus-free so `test_errors.py` needs no credentials and no
  network. `is_retryable` must never raise on an unknown string. `render` must emit lowercase
  `true`/`false` (or a consistent token) so the value is unambiguous — but the *parser* side is the
  subagent (the model), so exact machine round-trip is not required; readability + presence of the
  keywords (`type`, `retryable`, `attempted_query`) is what matters.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import errors; print(errors.is_retryable(errors.FAILURE_ACCESS_TIMEOUT), errors.is_retryable(errors.FAILURE_VALID_EMPTY))"`
  → prints `True False`.

### 2. CREATE `tests/test_errors.py`

- **IMPLEMENT:** Deterministic unit table: `is_retryable` True for `FAILURE_ACCESS_TIMEOUT` /
  `FAILURE_ACCESS`, False for `FAILURE_VALID_EMPTY` and for an unknown string; `ErrorEnvelope.render`
  contains `ERROR:`, the type, `retryable`, the echoed `attempted_query`, and the `failed_source`
  when set; a no-`failed_source` envelope still renders without raising.
- **PATTERN:** `tests/test_coverage.py` (parametrized pure-function table).
- **IMPORTS:** `import errors` (conftest puts `src/` on the path).
- **VALIDATE:** `../../.venv/bin/python -m pytest tests/test_errors.py -q`

### 3. UPDATE `src/config.py` — add `MAX_TOOL_RETRIES`

- **IMPLEMENT:** After `MAX_REFINEMENT_ITERATIONS` (L41), add:
  ```python
  #: Ceiling on a subagent's LOCAL retries of a retryable access failure before it propagates a
  #: structured failure to the coordinator (TR7). Referenced in the subagent prompts (the retry is
  #: model-driven — "local recovery" happens inside the subagent's own context, which the SDK runs
  #: opaquely). Named here as the single source of truth; precedent: MAX_REFINEMENT_ITERATIONS.
  MAX_TOOL_RETRIES = 2
  ```
- **PATTERN:** `src/config.py` L39-41 (`MAX_REFINEMENT_ITERATIONS` doc-comment style).
- **GOTCHA:** This is consumed by the prompt text (interpolated), not by orchestration code — so
  there is no code path that reads it besides the prompt-builders. That is intentional (matches how
  `CLASSIFIER_MODEL` is a defined-but-deferred seam, L26-28).
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config; print(config.MAX_TOOL_RETRIES)"` → `2`.

### 4. CREATE `src/provenance.py`

- **IMPLEMENT:** Pure, SDK-free (imports `schemas` only). Two public functions:
  - `parse_claims_block(report_text: str) -> list[schemas.Claim]`: find the first line equal to
    `CLAIMS:` (case-insensitive, stripped), then consume subsequent `- <claim text> [source: <name>,
    date: <date>, url: <url>]` lines until a blank/non-matching line. For each line, split the claim
    text from the bracketed metadata, parse `source`/`date`/`url` (tolerate missing `url` → `None`;
    tolerate missing `date` → `""`), and build `schemas.Claim(text=..., source=schemas.SourceRef(
    name=..., url=..., excerpt=<claim text or "">, date=...))`. Skip lines with no source (never
    raise). Return the list (possibly empty).
  - `build_report(report_text: str, coverage: dict, gaps: list) -> schemas.Report`: parse claims,
    build one section per facet is optional (sections can be a single `[{"body": report_text}]`
    stub — Phase 4's operative provenance surface is `claims` + `coverage` + `gaps`; full per-facet
    section splitting is NOT required by any acceptance criterion). Return
    `schemas.Report(sections=[{"body": report_text}], claims=<parsed>, coverage=coverage, gaps=gaps)`.
- **PATTERN:** `src/coverage_eval.py` `parse_coverage_block` L86-112 (header-then-`-`-lines,
  break on blank/non-matching, skip unmappable, never raise) — copy its control flow.
- **IMPORTS:** `import schemas`. `from dataclasses import ...` only if you add a local result type
  (not needed — return `schemas` types directly).
- **GOTCHA:** The bracket parse must be robust to the exact subagent line shape
  `- <text> [source: X, date: Y, url: Z]` (see `web_search.py` L38-40). Use a tolerant split: find
  the last `[` ... `]`; inside, split on `,` then each on the first `:`. Do NOT use a brittle full-
  line regex that fails if the claim text itself contains a comma or colon. If no bracket is found,
  skip the line (it is prose, not a claim). Keep `SourceRef.excerpt` = the claim text (the corpus
  excerpt is not re-fetched here) — `SourceRef` requires `excerpt` (non-default), so always provide
  it. `url` is `str | None`; pass `None` when absent, never the literal string `"None"`.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import provenance; cs=provenance.parse_claims_block('CLAIMS:\n- AI art market ~\$3.2B in 2024 [source: ArtMarket Report, date: 2024-11-01, url: https://x]'); print(len(cs), cs[0].source.name, cs[0].source.date)"`
  → `1 ArtMarket Report 2024-11-01`.

### 5. CREATE `tests/test_provenance.py`

- **IMPLEMENT:** Deterministic unit table:
  - a well-formed `CLAIMS:` block with 2–3 lines → N `Claim`s, each `.source` a `SourceRef` with the
    right `name`/`date`/`url`;
  - a line with no `url` → `SourceRef.url is None` (not `"None"`);
  - a claim whose text contains a comma → parsed correctly (tolerant split, not brittle regex);
  - no `CLAIMS:` block → `[]`;
  - a malformed line (no brackets) inside the block → skipped, others still parsed;
  - `build_report(...)` → `report.all_claims_have_source() is True` for a well-formed block (the FR5
    invariant on **parsed** claims), and passes `coverage`/`gaps` through unchanged;
  - an empty-claims report → `all_claims_have_source() is True` (vacuous) and `claims == []`.
- **PATTERN:** `tests/test_coverage.py` + `tests/test_schemas.py` (invariant assertions).
- **IMPORTS:** `import provenance`, `import schemas`.
- **VALIDATE:** `../../.venv/bin/python -m pytest tests/test_provenance.py -q`

### 6. UPDATE `src/tools/server.py` — timeout partitioning in `format_search`

- **IMPLEMENT:** Extend `format_search(query, facet=None)` (L61-75). After `hits = corpus.search(...)`:
  - Partition: `available = [d for d in hits if not d.get("timeout")]`,
    `unavailable = [d for d in hits if d.get("timeout")]`.
  - If `not hits`: existing valid-empty message (unchanged) — but make its wording clearly a
    *valid empty* (it already says so).
  - If `unavailable` and `available`: render the available hits (existing `_format_hit` loop) AND
    append a **partial** `ERROR:` block built from `errors.ErrorEnvelope(type=FAILURE_ACCESS_TIMEOUT,
    attempted_query=query, is_retryable=True, failed_source=unavailable[0]["source"], partial=[...],
    alternative="use the sources above; report the unavailable source as a gap")`. Prefix the whole
    thing so the model sees both: the found sources first, then the ERROR block.
  - If `unavailable` and not `available` (by-reference fetch of only D004): return a **full access
    failure** — no content lines, just the `ERROR:` block (type `access_timeout`, retryable,
    `failed_source`, `attempted_query`, alternative). No fabricated content.
  - Else (only `available`): existing clean render (unchanged).
  - Extend `_WEB_SEARCH_DESCRIPTION` (L38-52) to document that results may include an `ERROR:` block
    for an unavailable (timed-out) source, that this is **retryable and distinct from an empty
    result**, and that partial results above the block are still valid.
- **PATTERN:** existing `format_search` L61-75; `errors.ErrorEnvelope.render` from Task 1.
- **IMPORTS:** add `import errors` at the top of `server.py` (SDK-free; the standalone process
  already puts `src/` on the path L27-29, so a flat `import errors` resolves).
- **GOTCHA:** `format_search` is shared by BOTH server flavors (external stdio + the in-process
  `_web_search_in_process` L109-113), so the envelope reaches the coordinator's subagents AND the
  single-agent fallback. This is intended (the endpoint is down for everyone) but **changes the
  behavior of existing live tests** (Phase-2 single-agent music lookup, Phase-3 broad coverage) —
  see Risks; those live tests must be re-run. Do NOT mutate `mocks/corpus.py` — read `doc.get("timeout")`
  in the tool so the corpus stays data-only (per corpus docstring L17-19). Keep `format_search`
  pure (no I/O, no sleeping — do NOT actually block; "timeout" is *simulated* via the marker).
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from tools.server import format_search; print('---MUSIC---'); print(format_search('AI', facet='music')); print('---D004---'); print(format_search('Recording Artists Coalition'))"`
  → music shows D003 **and** an `ERROR:` block naming Recording Artists Coalition; the by-reference
  fetch shows only the `ERROR:` block (no content). D003's content ("10 million tracks") must still
  be present in the music output (music stays coverable).

### 7. UPDATE `tests/test_tools_web_search.py` — envelope cases

- **IMPLEMENT:** Add tests:
  - `test_timeout_source_yields_partial_with_error_block`: `format_search("AI", facet="music")`
    contains the D003 evidence (`"Music Industry Digest"` or `"10 million"`) **and** an `ERROR:`
    marker **and** `"Recording Artists Coalition"` **and** a retryable indicator; music is NOT lost.
  - `test_by_reference_timeout_is_full_access_failure`: `format_search("Recording Artists Coalition")`
    contains `ERROR:` / `access_timeout` and does **not** contain the RAC excerpt content (no
    fabricated content).
  - `test_access_failure_distinct_from_valid_empty`: the timeout ERROR block (retryable) is
    distinguishable from `format_search("zzzznotarealterm")` (the existing "No sources found" valid
    empty, which carries **no** `ERROR:`/retryable marker).
  - keep/verify existing tests still pass (film clean path has no ERROR block).
- **PATTERN:** existing `tests/test_tools_web_search.py` (assert on returned text substrings).
- **VALIDATE:** `../../.venv/bin/python -m pytest tests/test_tools_web_search.py -q`

### 8. UPDATE `src/coordinator.py` — `SYSTEM_PROMPT` contracts (CLAIMS + conflict + TR9 + source-unavailable)

- **IMPLEMENT:** Extend the existing `SYSTEM_PROMPT` (L70-121). Keep every current instruction
  (partitioning, back-to-back parallel dispatch, no "launched agents" early finish, `[source, date]`
  on every claim, the `COVERAGE:` block). ADD:
  - **Conflict/temporal (TR8):** "If two credible sources report DIFFERENT values for the SAME
    figure, present BOTH with their source and date — never silently pick one or average them. Note
    the temporal difference explicitly (e.g. an earlier vs. a later figure) so a change over time is
    not misread as a contradiction."
  - **Source-unavailable handling (TR7/TR9):** "If the search returns an `ERROR:` block reporting an
    unavailable (timed-out) source, do NOT fabricate its content and do NOT abort. Use whatever
    partial results you did get. A facet still counts as `covered` if you have solid evidence for it
    from other sources even when one source was unavailable — record the unavailable source in the
    Coverage & Gaps section below, NOT as a facet gap."
  - **TR9 rendering:** "Render QUANTITATIVE figures/statistics as a Markdown TABLE (columns: Metric,
    Value, Source, Date). Render QUALITATIVE analysis as prose. After the briefing body, add a
    `## Coverage & Gaps` section marking well-supported facets vs. areas limited by unavailable
    sources."
  - **CLAIMS block (TR8/FR5):** "After the COVERAGE report, emit a machine-readable claims list on
    its own lines in EXACTLY this format — one line per claim, every claim carrying its source and
    date (100% cited; a claim with no source does not belong here):
    ```
    CLAIMS:
    - <claim text> [source: <source name>, date: <YYYY-MM-DD>, url: <url>]
    ```
    Include the conflicting figures as separate claim lines (both sources)."
  - Order at the tail: briefing body (with table + prose + `## Coverage & Gaps`) → `COVERAGE:` block
    → `CLAIMS:` block.
- **PATTERN:** the existing `COVERAGE:` contract at L112-119 (exact-format machine-readable block);
  the subagent claim-line shape at `web_search.py` L38-40 (reuse it verbatim so the parser matches).
- **GOTCHA:** `SYSTEM_PROMPT` is ALSO used by `build_no_delegation_options()` (L298) — that is fine
  (the negative test only checks that no `Agent` block appears; the extra contracts are inert there).
  Do NOT add these contracts to `_SEQUENTIAL_SYSTEM_PROMPT` (benchmark baseline, keep verbatim —
  Phase 3 precedent L123-125) or to `_PARTIAL_SYSTEM_PROMPT` (its output goes through refinement,
  which ends on the full `SYSTEM_PROMPT`, so the final text carries the CLAIMS block anyway). Keep
  `_build_refinement_prompt` (L327-353) — but ADD to it: "re-emit the full COVERAGE block AND the
  full CLAIMS block" so a refined report still parses. The `CLAIMS:` and `COVERAGE:` headers must not
  collide with the parser's `-`-line consumption — they are separate blocks separated by a blank
  line (the coverage parser breaks on the blank line before `CLAIMS:`).
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from coordinator import SYSTEM_PROMPT; print(all(k in SYSTEM_PROMPT for k in ['CLAIMS:','COVERAGE:','Coverage & Gaps','different values' if 'different values' in SYSTEM_PROMPT.lower() else 'DIFFERENT']))"`
  (adjust keywords to your final wording; the real check is Task 12's unit test).

### 9. UPDATE `src/coordinator.py` — `_build_refinement_prompt` re-emit CLAIMS

- **IMPLEMENT:** In `_build_refinement_prompt` (L327-353), extend the final instruction so the
  refined full briefing re-emits BOTH the `COVERAGE:` block (already implied) AND the `CLAIMS:`
  block covering every claim (existing + newly added facets), preserving `[source, date]`.
- **PATTERN:** existing refinement-prompt text L336-353.
- **GOTCHA:** The refined report is the one `run_research` parses for `report`, so it MUST carry the
  CLAIMS block or `report.claims` will be empty after a refinement. Keep "do not lose any existing
  claim or source" (already present L343).
- **VALIDATE:** covered by Task 12/13 (prompt-string unit) + Task 14 (live).

### 10. UPDATE `src/agents/doc_analysis.py` + `src/agents/web_search.py` — retry + partial contracts

- **IMPLEMENT:**
  - `doc_analysis.py` prompt (L24-41): add a step — "If the `web_search` result contains an `ERROR:`
    block that is **retryable** (e.g. `access_timeout`), retry the SAME fetch up to
    `MAX_TOOL_RETRIES` times. If it STILL fails, do NOT fabricate: return a structured failure that
    states (a) the failure type, (b) the query you attempted, (c) any partial results you did
    obtain, and (d) an alternative (e.g. 'this specific source is unavailable — recommend annotating
    it as a gap'). This access failure is DISTINCT from a valid empty result (which means the corpus
    genuinely has no such source — report that as an empty finding, not a failure)."
  - `web_search.py` prompt (L24-41): add — "If the search returns partial results with an `ERROR:`
    block naming an unavailable source, USE the partial results and pass along the unavailable-source
    note (type, source, retryable) so the coordinator can annotate it. Retry once if the error is
    retryable before giving up on that source."
  - Interpolate the literal `2` or reference the number in prose (the prompt is a plain string; you
    may hardcode "up to 2" to match `config.MAX_TOOL_RETRIES` — add a comment tying them, since the
    prompt cannot import config cleanly at module load without care; simplest is the literal "1–2"
    with a `# keep in sync with config.MAX_TOOL_RETRIES` comment).
- **PATTERN:** existing subagent prompts (numbered "Do this:" steps) `web_search.py` L24-41,
  `doc_analysis.py` L25-40.
- **GOTCHA:** These are `AgentDefinition` prompt strings — keep the existing distilled-output
  contract (`CLAIMS:` sub-section, `[source: ..., date: ..., url: ...]` line shape) intact; the
  retry text is ADDITIVE. Do NOT change `model`, `tools`, `mcpServers`, or `background=True`.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from agents.doc_analysis import doc_analysis_agent; print('retry' in doc_analysis_agent.prompt.lower(), 'valid empty' in doc_analysis_agent.prompt.lower() or 'empty result' in doc_analysis_agent.prompt.lower())"`
  → `True True`.

### 11. UPDATE `src/loop.py` — add `AgentRun.report` field

- **IMPLEMENT:** Add `import schemas` near the top (SDK-free import; safe). Add a field to `AgentRun`
  (alongside `route`/`coverage`/`gaps` L103-109):
  ```python
  report: Optional["schemas.Report"] = None  # assembled provenance report (TR8/FR5), set by run_research()
  ```
- **PATTERN:** the post-hoc fields L103-109 (set by `run_research`, not the loop). Update the
  `AgentRun` docstring's "set by run_research()" note to include `report`.
- **GOTCHA:** `loop.py` currently does NOT import `schemas`; adding it is fine (`schemas` is
  SDK-free and already on the path). Use the string annotation `Optional["schemas.Report"]` OR a
  direct `Optional[schemas.Report]` — both work since `schemas` is imported. Do NOT set it in
  `_ingest_message` or `run_turn` (the loop stays report-agnostic, exactly like `route`).
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from loop import AgentRun; print(AgentRun().report)"` → `None`.

### 12. UPDATE `src/coordinator.py` — assemble + attach `run.report` in `run_research`

- **IMPLEMENT:** In `run_research` (L390-405):
  - Fan-out path (after `run = await _run_with_refinement(...)`, before `run.route = route`): build
    `run.report = provenance.build_report(run.final_text, run.coverage, run.gaps)`.
  - Single-agent path (after `run = await run_turn(...)`): attempt `provenance.build_report(
    run.final_text, {}, [])`; a narrow lookup usually has no CLAIMS block, so `report.claims` may be
    `[]` — that is acceptable (the single-agent contract is a one-sentence cited answer, not a
    structured claims list). Attaching a report with empty claims is harmless; `all_claims_have_source()`
    is vacuously True.
- **IMPORTS:** add `import provenance` at the top of `coordinator.py` (alongside `import coverage_eval`
  L34).
- **PATTERN:** the existing post-hoc stamping of `run.route` L401/L404 and coverage in
  `_run_with_refinement` L383-386.
- **GOTCHA:** Build the report from `run.final_text` (the LAST synthesis turn's text — already the
  refined full briefing). Do NOT parse per-turn history. Keep `_run_with_refinement` unchanged
  (coverage-focused); provenance assembly lives in `run_research` for separation of concerns.
- **VALIDATE:** covered by Task 14 (live) + a light import check:
  `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import coordinator; print(hasattr(coordinator,'provenance'))"` → `True`.

### 13. UPDATE `tests/test_coordinator_config.py` — prompt-contract assertions

- **IMPLEMENT:** Extend `test_system_prompt_carries_coverage_and_partitioning_contract` (or add a
  new test) asserting `SYSTEM_PROMPT` contains: `"CLAIMS:"`, the conflict instruction (a distinctive
  substring of your final wording, e.g. `"same figure"` or `"never silently pick"`), the TR9
  rendering instruction (e.g. `"table"` / `"Coverage & Gaps"`), and the source-unavailable rule
  (e.g. `"unavailable"`). Assert `_SEQUENTIAL_SYSTEM_PROMPT` does NOT contain `"CLAIMS:"` (baseline
  stays clean). Assert `_build_refinement_prompt("q","draft",["film"])` contains `"CLAIMS:"`.
- **PATTERN:** existing `tests/test_coordinator_config.py` L91-95.
- **IMPORTS:** import the extra names from `coordinator` (`_SEQUENTIAL_SYSTEM_PROMPT`,
  `_build_refinement_prompt`) as needed.
- **VALIDATE:** `../../.venv/bin/python -m pytest tests/test_coordinator_config.py -q`

### 14. CREATE `tests/test_phase4_reliability_live.py` — the acceptance demo (integration)

- **IMPLEMENT:** ONE broad `run_research(_BROAD_QUESTION)` call (bounds cost to ~1 Opus + Sonnet
  fan-out), then four structure assertions:
  - **No abort / graceful degrade (TR7):** `run.subtype == "success"`, `not run.terminated_by_cap`,
    `run.final_text.strip()` non-empty.
  - **Music covered despite the RAC timeout (TR7 single-source gap):**
    `run.coverage.get("music") == coverage_eval.STATUS_COVERED`, AND the report annotates the
    unavailable source — lenient: `"Recording Artists Coalition" in run.final_text` OR any of
    (`"unavailable"`, `"timed out"`, `"timeout"`) appears (the gap is annotated, not silent).
  - **Provenance / FR5 (TR8):** `run.report is not None`, `run.report.claims` non-empty,
    `run.report.all_claims_have_source() is True`.
  - **Conflict preserved (TR8):** both `"Film Tech Quarterly"` and `"Screen Production Institute"`
    in `run.final_text`; both dates `"2023-05-01"` and `"2025-03-01"` (or `"2023"`/`"2025"`) present;
    both figures `"40%"` and `"55%"` present — neither dropped.
  - **TR9 rendering:** a Markdown table present (`"|" in run.final_text` and a header-separator row
    with `"---"`), and a coverage-annotation section present (`"Coverage & Gaps"` or `"gap"`).
  - Optionally assert `{"Film Tech Quarterly","Screen Production Institute"}` ⊆
    `{c.source.name for c in run.report.claims}` (semi-deterministic conflict-in-provenance check).
- **PATTERN:** `tests/test_phase3_coverage_live.py` verbatim for the `pytestmark`/skip-guard/fixture
  usage; use the existing `run_research` fixture from `conftest.py`.
- **GOTCHA:** Structure-only, lenient keyword checks — never assert exact prose. Include
  `run.final_text[:600]` in assert messages for debugging. This IS the folded prompt-contract spike
  (Phase-3 precedent): if the coordinator does not emit a parseable CLAIMS block or downgrades music
  to a gap, THIS test catches it — iterate on `SYSTEM_PROMPT` wording, not on the test.
- **VALIDATE:** `../../.venv/bin/python -m pytest tests/test_phase4_reliability_live.py -m integration -q`
  (needs `claude` CLI or `ANTHROPIC_API_KEY`; ~one Opus coordinator run).

### 15. UPDATE `run_example.py` — surface provenance + reliability

- **IMPLEMENT:** After the existing coverage prints (L29-32), add (guard for `run.report is None`):
  ```python
  if run.report is not None:
      print("CLAIMS (FR5):", len(run.report.claims),
            "| all cited:", run.report.all_claims_have_source())
  ```
  Optionally print whether the unavailable source is annotated (a substring check on
  `run.final_text`).
- **PATTERN:** existing `run_example.py` L20-34 print style.
- **VALIDATE:** `../../.venv/bin/python run_example.py` (live; optional — the pytest suites are the
  gate). Confirm it prints a claims count > 0 and `all cited: True`, plus a report containing the
  film conflict table and the `## Coverage & Gaps` section.

### 16. UPDATE `_tasks/todo.md` — Phase 4 checklist + review

- **IMPLEMENT:** Append a `# Phase 4 — Reliability + Provenance (TR7/TR8/TR9)` section mirroring the
  Phase 1–3 structure: scope guardrails, the step checklist (checkable), a Validation block, and —
  after implementation — a Review section (outcome, what worked, what didn't + fixes, deliberate
  boundaries). Note whether any NEW SDK mechanic surfaced (expected: none — pure Python + prompt
  contracts, like Phase 3) and whether memory needs updating.
- **PATTERN:** `_tasks/todo.md` Phase 3 section (L210-304).
- **VALIDATE:** manual read-through; the checklist reflects reality.

---

## TESTING STRATEGY

### Unit Tests (default `pytest -m "not integration"`, deterministic, credential-free, ~fast)

- `test_errors.py` — `is_retryable` truth table (access/timeout True, valid_empty + unknown False);
  `ErrorEnvelope.render` contains the required keys; no-`failed_source` renders without raising.
- `test_provenance.py` — `parse_claims_block` builds `Claim`+`SourceRef` with correct name/date/url;
  `url` absent → `None`; comma-in-claim tolerated; no block → `[]`; malformed line skipped;
  `build_report` → `all_claims_have_source() is True` and passes coverage/gaps through.
- `test_tools_web_search.py` (extended) — timeout facet sweep → partial (D003 + ERROR block + RAC +
  retryable); by-reference D004 → full access failure (ERROR, no content); access-failure distinct
  from valid-empty; clean facet unchanged.
- `test_coordinator_config.py` (extended) — `SYSTEM_PROMPT` carries CLAIMS + conflict + TR9 +
  source-unavailable contracts; `_SEQUENTIAL_SYSTEM_PROMPT` stays CLAIMS-free; refinement prompt
  re-emits CLAIMS.
- Existing suites (`test_coverage`, `test_schemas`, `test_triage`, `test_loop_task_parsing`,
  `test_config`) must stay green (the `report` field + `MAX_TOOL_RETRIES` are additive).

### Integration Tests (`pytest -m integration`, live, ~1 Opus + Sonnet fan-out)

- `test_phase4_reliability_live.py` — one broad run → four assertions (no-abort + music-covered-
  with-annotation + provenance/FR5 + conflict-preserved + TR9-render).
- **Full live regression required this phase:** re-run `tests/test_phase1_spine_live.py`,
  `test_phase2_parallel_live.py`, `test_phase3_coverage_live.py`. The timeout activation in
  `format_search` changes what music/single-agent queries return (partial + ERROR block), so these
  must be confirmed still green (or their lenient assertions adjusted for the new partial behavior —
  see Risks). Do NOT defer this (Phase 3 deferred it because it changed nothing behavioral; Phase 4
  changes retrieval behavior).

### Edge Cases

- A claim line whose text contains `,` or `:` (tolerant split, not brittle regex).
- A `CLAIMS:` block with a malformed line among good ones (skip the bad, keep the good).
- `url:` missing from a claim line → `SourceRef.url is None`.
- The music facet: D003 present AND RAC ERROR block present in one `format_search` return (partial).
- By-reference fetch of D004 alone → full access failure with no content (no fabrication).
- Valid empty (`"zzzznotarealterm"`) carries NO ERROR/retryable marker (distinct from access
  failure).
- Refinement turn: the refined report still carries a parseable CLAIMS block (so `report.claims` is
  non-empty after refinement).
- Single-agent route: `run.report` attached with possibly-empty claims → `all_claims_have_source()`
  vacuously True, no crash.

---

## VALIDATION COMMANDS

Run from `projects/multi-agent-research-agent/`. Venv python: `../../.venv/bin/python`.

### Level 1: Syntax & Import Sanity
```
../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import errors, provenance, config, schemas; from tools.server import format_search; from loop import AgentRun; import coordinator; print('imports ok')"
```

### Level 2: Unit Tests (must be green + fast, credential-free)
```
../../.venv/bin/python -m pytest -m "not integration" -q
```
Expected: all prior unit tests (82 at Phase-3 close) + the new `test_errors.py` /
`test_provenance.py` + extended tool/config tests, green in ~1–2s.

### Level 3: Integration Tests (live; needs `claude` CLI or ANTHROPIC_API_KEY)
```
../../.venv/bin/python -m pytest tests/test_phase4_reliability_live.py -m integration -q
../../.venv/bin/python -m pytest -m integration -q   # FULL Phase 1–4 live regression (required)
```

### Level 4: Manual Validation (end-to-end)
```
../../.venv/bin/python run_example.py
```
Confirm: `ROUTE: fan_out`; `CLAIMS (FR5): <N>0> | all cited: True`; the printed report contains a
Markdown table for the film-adoption figures showing BOTH 40% [Film Tech Quarterly, 2023] and 55%
[Screen Production Institute, 2025]; a `## Coverage & Gaps` section annotating the Recording Artists
Coalition as unavailable while music remains covered; a trailing `COVERAGE:` block (all 4 covered)
and a `CLAIMS:` block.

### Level 5: Additional Validation (optional)
- `/code-review` on the diff before committing (correctness + reuse).
- `git diff --stat` — confirm `mocks/corpus.py` is UNCHANGED (timeout handled in the tool, not the
  data) and `_SEQUENTIAL_SYSTEM_PROMPT` is UNCHANGED.

---

## ACCEPTANCE CRITERIA

- [ ] `errors.py` distinguishes access failure (retryable) from valid empty (not retryable);
      unit-tested. (TR7)
- [ ] `format_search` returns a structured `ERROR:` envelope for the timed-out endpoint: **partial**
      (D003 + RAC-unavailable note) on a music sweep, **full access failure** on a by-reference D004
      fetch; both distinct from a valid empty result; unit-tested. (TR7)
- [ ] Subagent prompts instruct 1–2 local retries on a retryable error, then a structured failure;
      asserted as a prompt contract. (TR7)
- [ ] A live broad run degrades gracefully on the timeout: `subtype == "success"`, not
      `terminated_by_cap`, music still `covered`, RAC annotated as unavailable — no abort, no silent
      empty. (TR7 / PRD §11)
- [ ] `run.report` is a `schemas.Report` with parsed `Claim`+`SourceRef` (claim, source, excerpt,
      date); `run.report.all_claims_have_source() is True` on a live run. (TR8 / FR5)
- [ ] The D007/D008 conflict pair both appear with sources + dates + both figures; neither dropped,
      neither silently resolved; asserted on structure. (TR8)
- [ ] The report renders figures as a Markdown table and analysis as prose, with a `## Coverage &
      Gaps` annotation section. (TR9)
- [ ] `CLAIMS:` block is a machine-readable contract in `SYSTEM_PROMPT` and re-emitted on
      refinement; parsed by the pure `provenance.parse_claims_block`. (TR8)
- [ ] Full unit suite green + fast; full `-m integration` (Phase 1–4) green (or lenient assertions
      adjusted for the new partial behavior, documented in the review).
- [ ] `mocks/corpus.py` unchanged (data-only); `_SEQUENTIAL_SYSTEM_PROMPT` unchanged (baseline).
- [ ] No new package-relative imports; snake_case throughout; existing names reused verbatim.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (Foundation → Core → Integration → Testing).
- [ ] Each task's VALIDATE command passed immediately.
- [ ] Level 1–4 validation commands all pass.
- [ ] Full unit suite (`-m "not integration"`) green; full live suite (`-m integration`) green.
- [ ] `run_example.py` shows FR5 (all cited: True), the conflict table, and the RAC annotation.
- [ ] `_tasks/todo.md` Phase 4 checklist + review appended.
- [ ] Memory reviewed (update `mar-agent-sdk-delegation` only if a NEW SDK mechanic surfaced —
      expected: none).
- [ ] Diff reviewed for quality; corpus + sequential baseline confirmed unchanged.

---

## NOTES

**No new SDK mechanic (like Phase 3).** Phase 4 is pure Python (`errors.py`, `provenance.py`,
`format_search` partitioning) + four prompt contracts. The only live-dependent risk is whether the
coordinator (a) emits a parseable `CLAIMS:` block, (b) keeps music `covered` while annotating the RAC
gap rather than downgrading the facet, (c) preserves both conflict figures, and (d) renders a table +
annotation section. Per the Phase-3 precedent, the prompt-contract "spike" is FOLDED INTO the live
test (Task 14) rather than a separate throwaway run, to save a paid run. If the contract does not
hold first try, iterate on `SYSTEM_PROMPT` wording — not on the test.

**Key design trade-offs (locked with the user):**
- *Single-source gap, not facet gap.* The timeout keeps music covered (D003) and annotates the one
  unavailable source (RAC/D004). This keeps TR7 partial-results orthogonal to TR4/TR5 facet
  coverage and avoids burning refinement iterations on a permanently-failing facet. Consequence: the
  coordinator prompt must explicitly say "one unavailable source ≠ a facet gap," or the model may
  downgrade music.
- *Prompt-driven retry, deterministic envelope.* The SDK runs subagent tool loops opaquely (TR6
  isolation), so "local recovery (1–2 retries)" lives in the subagent prompt (model-driven,
  validated via the prompt contract + graceful live degradation), while the envelope + the
  access-vs-empty distinction are pure and unit-tested. We do NOT assert a live retry count (the
  loop cannot see subagent-internal tool calls).
- *Prompt-driven conflict handling.* Code-based "same-figure" detection is too semantically fragile;
  the contract lives in the prompt and is asserted on structure (both sources + both dates + both
  figures present).
- *Coordinator-owned synthesis + rendering.* No new `synthesis`/`report` subagents (honors the
  Phase-1 decision), despite PRD §7.1 listing them — TR9 rendering is a prompt contract.

**Behavioral ripple into existing live tests (the main risk).** Activating the timeout in the shared
`format_search` changes what music/single-agent queries return (now includes an `ERROR:` block).
Re-run the FULL `-m integration` suite: (1) the Phase-2 single-agent music-track lookup still gets
D003 and should still answer/cite it (the ERROR block is additive); (2) the Phase-3 broad-coverage
test asserts `music == covered` — this must still hold given D003 + the "one unavailable source ≠
facet gap" prompt rule. If either regresses, adjust the coordinator prompt (preferred) or soften the
affected live assertion (documented in the review), NOT the corpus.

**What Phase 4 deliberately does NOT do.** Full per-facet `Report.sections` splitting (a single
`{"body": text}` stub suffices — no acceptance criterion needs structured sections); a real
(non-simulated) timeout / network I/O (the marker is simulated, no actual blocking); a
non-timeout access-failure taxonomy beyond the two constants; the stretch goals (fork_session,
crash-recovery manifests, LLM-judge). These are out of MVP scope (PRD §4 Out-of-Scope, §13).

**Confidence: 8.5/10 for one-pass success.** The pure modules (errors, provenance) and the
`format_search` envelope are fully specified and deterministically testable — near-certain. The
residual risk is the live prompt contract (does the Opus coordinator emit a clean CLAIMS block, keep
music covered, and render the table/annotations on the first wording?), which may need 1–2 rounds of
`SYSTEM_PROMPT` tuning — exactly the risk the folded live spike is designed to surface cheaply.
```
