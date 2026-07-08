# Feature: Phase 3b — Test Generation (FR2)

The following plan should be complete, but it's important that you **validate documentation, codebase patterns,
and task sanity before you start implementing**. Pay special attention to the naming of existing utils, types, and
models from Phases 1–3a — **import from the right files** (`from parse import Finding, Location`), and do **not**
reshape the existing review contract (`FINDINGS_SCHEMA`, `Finding`, `invoke_claude`, `parse_result`, `dedupe`,
`store`, `workspace`). Test-gen is an ADDITIVE second output path alongside review — it must not disturb any
Phase-1/2/3a behavior.

> **PREREQUISITE — verify first.** Phases 1, 2, and 3a are implemented and committed (branch
> `feat/ci-review-bot-scaffold`, offline suite **80 passed, 11 deselected**, working tree clean). This plan builds
> directly on that spine and reuses `runner`, `workspace`, `config`, `severity`'s pure-module discipline, and the
> `dedupe`/`store` two-layer pattern. The first task re-verifies the interfaces below against the **actual code on
> disk** and adapts if anything drifted — the real code wins over this plan.

> **Ground-truth already established (do not re-derive):**
> - The "agent" is the **Claude Code CLI** (`claude -p`), never the SDK/Messages API. Test-gen is another headless
>   `claude -p --output-format json --json-schema` call — **TR1** (headless, no hang) and **TR2** (schema is the
>   contract) apply verbatim. NO `anthropic` / `claude-agent-sdk` / `gh` imports.
> - `claude -p` auto-loads `CLAUDE.md` from `cwd` + ancestors — the **TR3** context channel. Test-gen reuses
>   `workspace.staged(...)` so the reviewed project's testing standards (a new section in the fixture `CLAUDE.md`)
>   reach the run. Do NOT re-solve isolation — reuse Phase-2's `workspace.py`.
> - Every `claude -p` invocation is a fresh independent process (**TR7**). Test-gen is a single independent pass
>   (one file's change + its existing tests → suggestions); it does not need multi-pass fan-out.
> - **The FR2 skip-covered guarantee mirrors the proven Phase-3a TR8 two-layer dedupe design exactly**: a
>   *prompt-context* layer (existing tests fed into the prompt → model proposes only uncovered cases — the semantic
>   layer) backed by a *structural* deterministic layer (`skip_covered` by test-name collision + within-run `case`
>   dedupe — the offline-testable guarantee). This is intentional symmetry with `dedupe.py`.

> **SCOPE — Phase 3b only.** This plan covers **FR2** (generate net-new tests for changed code, skipping
> already-covered cases). **OUT OF SCOPE (do not build):** `detected_pattern` dismissal tracking + category
> quarantine (TR9/FR4 — Phase 4); real `gh --post` posting (Phase 4). Test-gen stays **emit-only** (prints proposed
> tests), exactly as review does.

---

## Feature Description

Phase 3b adds the second deliverable the PRD groups under "test generation" (PRD §4, §7 "Test Generation", §12
Phase 3, FR2): given a changed-code diff **and the existing tests for that code**, the bot proposes **net-new**
tests for the changed behavior and **skips cases already covered** by the existing tests. It is a distinct output
path from review — a different output schema (`tests`, not `findings`), a different versioned command
(`.claude/commands/test-gen/`), and a distinct fixture — but it reuses the entire Phase-1/3a spine: the headless
`claude -p` runner (TR1), schema-constrained structured output (TR2), CLAUDE.md-as-context via a staged workspace
(TR3), and the two-layer dedupe discipline (prompt-context + structural backstop) proven in Phase 3a.

The headline acceptance (PRD §5 User Story 6): *"Given existing tests for the happy path, test-gen proposes only
the untested error-path cases."* On the fixture, a correct `apply_discount(price, rate)` has its happy path already
covered by an existing `test_apply_discount_basic`; test-gen must propose a test for the **uncovered** out-of-range
(`ValueError`) branch and must **not** re-propose the happy path.

## User Story

As a **developer who just changed a function that already has some tests**,
I want the bot to **suggest tests only for the behaviors my existing tests don't already cover**,
So that **I get net-new coverage for the risky, untested paths without wading through duplicate suggestions for
cases I've already tested** — the same trust discipline the reviewer applies to duplicate comments, applied to
test suggestions.

## Problem Statement

Phase 3a made review scale and stop spamming duplicate comments, but FR2 — test generation — was explicitly
deferred (`_tasks/todo.md` Phase-3a review: *"FR2 test-gen is Phase 3b"*; the Phase-3a plan's SCOPE note). Today
`make test-gen` is a stub that echoes `"not implemented (Phase 3)"` (`Makefile:22–23`), there is no test-gen
schema, no test-gen command, no `testgen` module, and no test-gen fixture. A naive test generator that re-suggests
already-covered cases is the test-gen analog of the duplicate-comment trust-killer the whole project exists to
prevent: a developer who sees the bot propose a test they already wrote will mute it.

## Solution Statement

Add a **distinct test-gen output schema** (`TESTGEN_SCHEMA` in a new `testgen_schema.py`, sibling to `schema.py`)
and a **new module `testgen.py`** that mirrors the review side's pure/live split:

- **Pure core (offline, deterministic, never raises):** `existing_test_names` (regex-extract `def test_…` names
  from an existing test file), `dedupe_suggestions` (collapse suggestions sharing a `case` slug, keep-first —
  the within-run layer), `skip_covered` (split suggestions into `(new, skipped)` by test-name collision against
  the existing tests — the cross-existing structural backstop, returning the same `(new, still)`-shaped tuple as
  `dedupe.suppress_prior`), `parse_testgen` (CLI event-stream → `TestSuggestion` objects, mirroring
  `parse.parse_result`), and `score_testgen` (a small scorer over a testgen ground-truth).
- **Live driver:** `generate_tests(diff_text, existing_tests_text, …)` composes the versioned prompt (substituting
  `{diff}` and `{existing_tests}`), runs one headless `claude -p` pass via `runner.invoke_claude`, parses, and
  dedupes within-run — then the caller applies `skip_covered`. Plus a demo driver `run_testgen_demo()` for
  `make test-gen`, mirroring `metrics.run_metrics` / `multipass.run_multipass_demo`.

The **FR2 skip is two-layer, mirroring Phase-3a dedupe**: the prompt feeds the existing test bodies in and
instructs the model to propose only uncovered cases (the *semantic* layer — handles renamed/reworded coverage);
the pure `skip_covered` + `dedupe_suggestions` are the *deterministic backstop* (offline-testable, the FR2
guarantee that a covered case is never re-emitted). A new `fixtures/testgen-sample/` repo (correct `discount.py` +
existing happy-path `test_discount.py` + a `CLAUDE.md` testing-standards section + `testgen.diff` +
`testgen_ground_truth.json`) is the ground-truth harness, scored with `score_testgen`. All orchestration is
unit-tested **offline** by monkeypatching `testgen.runner.invoke_claude` (proving the single-call shape, the
prompt carries both diff + existing tests, and the parse/dedupe/skip logic — zero tokens); the real-model behavior
(proposes the uncovered case, skips the covered one) is `integration`-marked on the cheap haiku tier.

## Feature Metadata

**Feature Type**: New Capability (a second output path — test generation — alongside review)
**Estimated Complexity**: Medium (low algorithmic complexity; the care is in a clean second schema/parser without
reshaping the review contract, honest two-layer skip semantics, offline-testable orchestration via monkeypatch,
and a fixture whose "covered vs uncovered" split is unambiguous)
**Primary Systems Affected**: `src/review/` (new `testgen_schema.py`, `testgen.py`; modify `config.py`,
`workspace.py` [one-line exclusion glob generalization]), `.claude/commands/test-gen/` (new `generate-tests.md`),
`fixtures/testgen-sample/` (new fixture repo), `tests/` (new offline + integration), `Makefile` (`test-gen` stub →
demo driver)
**Dependencies**: none new — `jsonschema`, `python-dotenv`, `pytest` already in the shared venv (`../../.venv`).
Claude Code CLI on PATH is the agent under test.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**Phase-1/2/3a code in THIS repo (read the ACTUAL files; line numbers current as of planning):**

- `src/review/schema.py` (whole file, 20–58 `FINDINGS_SCHEMA`, 61–63 `as_json_string`, 66–73
  `validate_findings_obj`) — **the template for `testgen_schema.py`**. Note the module docstring's key point:
  `--json-schema` maps the **top-level object** to a tool input schema, so the top level MUST be an object with a
  named array property (`{"type":"object","required":["tests"],"properties":{"tests":{...}}, "additionalProperties":False}`),
  **never a bare array**. Mirror `as_json_string`/`validate_*` exactly.
- `src/review/parse.py` (whole file; 20–22 `ParseError`; 24–41 `Location`/`Finding`; 44–52 `ParsedReview`; 54–128
  `parse_result`) — **the template for `parse_testgen`**. `parse_result` finds the `type=="result"` event, handles
  `is_error`, prefers `structured_output` then falls back to `json.loads` on the `result` string, validates against
  the schema, then materializes dataclasses. `parse_testgen` mirrors this **verbatim in shape** but builds
  `TestSuggestion` objects and validates against `TESTGEN_SCHEMA`. **Do NOT modify `parse.py`** — duplicate the
  ~15-line event-locating logic (the established house pattern: `dedupe._same_file` is copied from
  `metrics._same_file`, `_strip_frontmatter` is copied in `cli`/`metrics`/`multipass`). Note the origin in a comment.
- `src/review/runner.py` (28–74 `invoke_claude(prompt, schema_json, model, timeout_s, cwd=None) ->
  RunResult(stdout, stderr, returncode)`) — test-gen calls this once. **Signature is final — do not change it.**
  Monkeypatch `testgen.runner.invoke_claude` in offline tests. `RunResult` (14–25) is the canned-output shape.
- `src/review/dedupe.py` (whole file; 41–61 `is_duplicate`; 64–77 `dedupe` keep-first; 80–105 `suppress_prior` →
  `(new, still)`) — **the pattern `skip_covered` / `dedupe_suggestions` mirror**. `suppress_prior`'s
  `(new, still_unresolved)` tuple shape is exactly what `skip_covered` returns as `(new, skipped)`. `dedupe`'s
  keep-first stable collapse is what `dedupe_suggestions` does over the `case` slug. Copy the *shape and docstring
  discipline* (pure, total, deterministic, stdlib-only, never raises), not the finding-specific logic.
- `src/review/store.py` (whole file; 22–31 `_pr_id`; 55–71 `save_findings`; 74–89 `load_prior`) — the mkdir +
  json read/write + `base_dir` override idiom. Phase 3b does NOT persist test suggestions across runs (no re-run
  dedupe for test-gen in the MVP — the existing-tests file IS the "prior"), so **you do not add to `store.py`**;
  it's referenced only for the write-json idiom the demo driver reuses (`metrics._write_metrics` is the closer
  template).
- `src/review/workspace.py` (whole file; 27–33 `STAGE_EXCLUDE`/`_EXCLUDE_GLOBS`; 36–63 `stage_workspace`; 83–94
  `staged`) — reuse `workspace.staged(repo, include_claude_md)` for the test-gen live driver. **The ONE change
  here:** generalize `_EXCLUDE_GLOBS`' `"ground_truth.json"` entry to `"*ground_truth.json"` so the new
  `testgen_ground_truth.json` answer key is never staged into the model's workspace (the glob still matches the
  original `ground_truth.json`, so review staging is byte-for-byte unaffected — assert this in a test).
- `src/review/metrics.py` (whole file — especially 49–54 `_same_file`; 188–222 `run_variant`; 225–251
  `_load_cases`/`_write_metrics`; 254–277 `run_metrics`) — **the template for the test-gen live driver + demo**:
  `run_variant`'s staged-workspace → `invoke_claude(cwd=…)` → parse shape; `_write_metrics`'s
  `METRICS_DIR.mkdir(...)` + `json.dumps(..., indent=2)`; `run_metrics`'s demo-driver shape (local imports inside
  the function, print + write JSON, return dict). `_same_file` is the suffix-tolerant path match `score_testgen`
  reuses for target-file matching.
- `src/review/config.py` (whole file; 22–23 `PROJECT_ROOT`; 27 `PROMPT_TEMPLATE`; 40 `CLAUDE_TIMEOUT_S`; 44–61
  fixture/metrics constants; 57 `METRICS_DIR`; 61 `LINE_MATCH_TOLERANCE`) — you ADD the test-gen constants here
  (`TESTGEN_PROMPT`, `TESTGEN_REPO`, `TESTGEN_GROUND_TRUTH`, `TESTGEN_DIFF_NAME`, `TESTGEN_EXISTING_TESTS_NAME`),
  reusing `PROJECT_ROOT`. Reuse `METRICS_DIR` for the demo's output JSON (it already holds `multipass.json`, etc.).
- `src/review/post.py` (12–29 `format_comment`/`emit`) — the template for a small `format_test`/`emit_tests` in
  `testgen.py` (do NOT modify `post.py`; add the test-gen emit helpers inside `testgen.py` since they format a
  different object).
- `.claude/commands/review/review-diff.md` (whole file) — **the template for `generate-tests.md`**: mirror its
  frontmatter (`---\ndescription: …\n---`), the "honor the project `CLAUDE.md`" clause (lines 10–13), the
  emit-only-through-structured-output rule (15–17), the few-shot discrimination format (39–56), and the
  field-guidance + fenced ` ```diff\n{diff}\n``` ` placeholder tail (75–92). Change the *task* (propose net-new
  tests, skip covered cases) and add a second ` ```python\n{existing_tests}\n``` ` block.
- `.claude/commands/review/review-integration.md` (whole file) — a second example of a versioned command mirroring
  `review-diff.md` with a changed scope; confirms the house prompt style before you author a third.
- `fixtures/sample-repo/CLAUDE.md` (whole file) — the reviewed-project CLAUDE.md pattern (domain conventions +
  review policy + severity policy). The new `fixtures/testgen-sample/CLAUDE.md` mirrors this shape but carries
  **testing standards** (the test-gen TR3 context channel) instead of review policy.
- `fixtures/sample-repo/pr.diff` (whole file) — the exact unified-diff shape the fixture `testgen.diff` must
  follow (`diff --git a/… b/…`, `new file mode`, `--- /dev/null`, `+++ b/…`, `@@ -0,0 +1,N @@`, `+` lines).
- `fixtures/sample-repo/ground_truth.json` (whole file) — the answer-key shape `testgen_ground_truth.json` adapts
  (a `cases` array; each case a dict with a stable id and a `should_*` boolean + a `note`).
- `tests/test_multipass.py` (whole file — especially 43–70 `_canned`/`_make_fake` monkeypatch harness; 113–137 the
  call-count + prompt-content assertions) — **the template for the offline orchestration test**: build a canned
  `runner.RunResult` with a valid CLI event array, `monkeypatch.setattr(testgen.runner, "invoke_claude", fake)`,
  assert the call count (exactly 1 for test-gen) and that the prompt contains both the diff and the existing tests.
- `tests/test_schema.py` — the offline schema-validation test shape to mirror for `testgen_schema` (valid object
  passes; missing required field / bad type raises `jsonschema.ValidationError`; round-trip via `as_json_string`).
- `tests/test_parse.py` — the golden-fixture parse test shape to mirror for `parse_testgen` (golden stdout →
  suggestion; is_error envelope; structured_output vs result-string fallback; malformed → `ParseError`).
- `tests/test_dedupe.py` (whole file; 12–20 `_f` builder; the `is_duplicate`/`dedupe`/`suppress_prior` assertions)
  — the offline pure-logic test shape to mirror for `dedupe_suggestions`/`skip_covered`.
- `tests/test_store.py` (whole file) — the `tmp_path`/`base_dir` discipline (never write the repo store) — relevant
  if the demo writes JSON; use `METRICS_DIR` via the driver, and in tests assert on returned structure not files.
- `tests/test_precision_live.py` (whole file; 21–27 `pytestmark`; 47–65 `_flagged`/assert-on-outcomes) — **the
  template for `test_testgen_live.py`**: `pytestmark = [pytest.mark.integration, pytest.mark.skipif(shutil.which(
  "claude") is None, …)]`, `model=config.BASELINE_MODEL` (haiku), assert on outcomes/direction NEVER on model prose.
- `tests/conftest.py` (15–27 `sys.path` + `claude_runnable`; 30–65 fixtures) — reuse; add a `sample_testgen_output`
  fixture if convenient (or read the golden file directly in the test, mirroring `sample_output`).
- `tests/fixtures/sample_claude_output.json` (whole file) — the real CLI event-array shape to imitate for the new
  golden `tests/fixtures/sample_testgen_output.json` (a `system` init event + a `result` event with both
  `structured_output` and a `result` JSON string).

**Sibling house-style references (mirror the DISCIPLINE, verified in Phases 2–3a):**
- `../multi-agent-research-agent/src/coverage_eval.py` — the canonical pure/total/deterministic/never-raises module
  docstring + string-constants + `@dataclass` result-struct style. `testgen.py`'s pure section and `testgen_schema.py`
  follow it (same style `severity.py`/`dedupe.py`/`metrics.py` already follow — match those in-repo precedents).
- `../multi-agent-research-agent/tests/test_coverage.py` — parametrized offline assertions on structure/constants.

### New Files to Create

```
claude-code-ci-review-bot/
├── .claude/commands/test-gen/
│   └── generate-tests.md              # NEW: versioned test-gen prompt (net-new tests, skip covered; {diff} + {existing_tests})
├── src/review/
│   ├── testgen_schema.py              # NEW: TESTGEN_SCHEMA (distinct from FINDINGS_SCHEMA) + as_json_string + validate_tests_obj (TR2)
│   └── testgen.py                     # NEW: TestSuggestion/parse_testgen; pure existing_test_names/dedupe_suggestions/skip_covered/score_testgen; live generate_tests + run_testgen_demo (FR2)
├── fixtures/testgen-sample/           # NEW: test-gen ground-truth harness (separate from the review sample-repo)
│   ├── CLAUDE.md                      # NEW: testing standards = the test-gen TR3 context channel
│   ├── src/discount.py               # NEW: a CORRECT function with a guarded error branch (the change under test)
│   ├── tests/test_discount.py        # NEW: existing test covering ONLY the happy path (the "already covered" context)
│   ├── testgen.diff                  # NEW: the unified diff of the change under test (discount.py)
│   └── testgen_ground_truth.json     # NEW: answer key — happy-path=should_propose:false, error-path=should_propose:true
└── tests/
    ├── fixtures/sample_testgen_output.json   # NEW: recorded golden test-gen CLI output for offline parse tests
    ├── test_testgen_schema.py        # OFFLINE: TESTGEN_SCHEMA validity + enum/required enforcement + round-trip
    ├── test_testgen.py               # OFFLINE: parse_testgen + existing_test_names + dedupe_suggestions + skip_covered + score_testgen + orchestration via monkeypatch
    └── test_testgen_live.py          # [integration] proposes the uncovered error-path case; skips the covered happy path
```

### Files to Modify

```
├── src/review/config.py               # ADD test-gen path/fixture constants (reuse PROJECT_ROOT, METRICS_DIR)
├── src/review/workspace.py            # ONE-LINE: _EXCLUDE_GLOBS "ground_truth.json" -> "*ground_truth.json" (never stage the testgen answer key)
└── Makefile                           # test-gen stub -> PYTHONPATH=$(PYTHONPATH) $(PY) -c "import testgen; testgen.run_testgen_demo()" + LIVE-call comment
```

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Claude Code Headless mode](https://code.claude.com/docs/en/headless) — `-p` / `--output-format json` /
  `--json-schema` reference. Why: test-gen is one such call; confirms `-p` is a fresh non-interactive session
  (TR1/TR7). Unchanged from Phase 1/2/3a.
- [Claude Code Memory / CLAUDE.md loading](https://code.claude.com/docs/en/memory) — Why: confirms the staged
  workspace governs which `CLAUDE.md` (now carrying testing standards) the test-gen pass loads (TR3). No change to
  `workspace.py`'s staging mechanism beyond the exclusion glob.
- No new external libraries. `re` (test-name extraction), `ast`/`compile` (optional syntactic check of generated
  test code in the integration test), `json`, `pathlib` are all stdlib.

### The FR2 architecture (the crux — mirror of Phase-3a dedupe's two layers)

```
     testgen.diff (discount.py change)        tests/test_discount.py (existing: happy path only)
                 │                                          │
                 └───────────────┬──────────────────────────┘
                                 ▼
              generate-tests.md prompt:  {diff}  +  {existing_tests}
              "propose net-new tests; DON'T re-propose cases the existing tests already cover"
                                 ▼
              ONE fresh claude -p pass (TR1/TR2/TR7), cwd = staged testgen-sample (TR3: testing standards)
                                 ▼  structured_output.tests  (parse_testgen → [TestSuggestion])
              ┌──────────────────┴───────────────────────────────────────────┐
              │  LAYER 1 (semantic, in-prompt): model already skipped the      │
              │  happy path because it saw test_apply_discount_basic           │
              └──────────────────┬───────────────────────────────────────────┘
                                 ▼
              dedupe_suggestions(...)   ← within-run: collapse suggestions sharing a `case` slug (keep-first)
                                 ▼
              skip_covered(suggestions, existing_test_names(test_discount.py))
                                 │        ← LAYER 2 (structural backstop, deterministic, offline-testable):
                                 │          drop any suggestion whose test_name collides with an existing test
                                 ▼
              (new = [test for rate-out-of-range ...], skipped = [any happy-path dupe])
                                 ▼
              emit_tests(new)   +   score_testgen(new, testgen_ground_truth.cases)
                                 ▼
              headline: happy-path NOT proposed (skipped); error-path IS proposed (net-new)
```

**Why the fixture split is unambiguous:** `apply_discount(price, rate)` is **correct** (guarded `ValueError` on
out-of-range `rate`, returns `price * (1 - rate)` otherwise). The existing `test_apply_discount_basic` covers only
the happy path (`apply_discount(100, 0.1) == 90`). The uncovered behavior is the `ValueError` branch (rate < 0 or
> 1) and the boundaries (rate == 0, rate == 1). A trustworthy test-gen proposes the error-path test and does NOT
re-propose the happy path. Unlike the review fixture, the target has **no seeded bug** — test-gen's job is coverage,
not bug-finding, so a clean function keeps the "covered vs uncovered" signal unambiguous.

### Patterns to Follow

**Naming (Python — snake_case):** functions/vars `snake_case`, dataclasses `PascalCase` (`TestSuggestion`,
`Target`, `ParsedTestGen`, `TestGenResult`), module constants `UPPER_SNAKE` (`TESTGEN_SCHEMA`). String constants,
not enums (repo precedent: `severity.SEVERITY_LEVELS`).

**Distinct-schema, same-contract-discipline (mirror `schema.py`):** `testgen_schema.py` is a *second* canonical
schema — top-level object, one named array (`tests`), `additionalProperties: False`, fed to `--json-schema` AND
used post-hoc to `validate_tests_obj`. Schema drives both sides so the CLI contract and the parser can't drift.

**Pure-core / live-driver split within one module (mirror `metrics.py`/`multipass.py`):** `testgen.py` keeps the
pure functions (`existing_test_names`, `dedupe_suggestions`, `skip_covered`, `score_testgen`, `parse_testgen`) —
importing only stdlib + `testgen_schema` — clearly separated from the live driver (`generate_tests`,
`run_testgen_demo`) which does the `claude -p` call. Import `runner`, `schema`-style deps at the **top** of the
module (none touch the CLI at import time) so tests can `monkeypatch.setattr(testgen.runner, "invoke_claude", fake)`.

**Pure-module docstring + contract (mirror `dedupe.py:1–24`, `severity.py:1–20`):** open `testgen.py`'s pure
section (and `testgen_schema.py`) with a docstring stating *pure, total, deterministic, stdlib-only, never raises,
unit-tests offline with no CLI/credentials* — for the functions that qualify.

**Path-suffix normalization (reuse `metrics._same_file`, lines 49–54):** `score_testgen` matches a suggestion's
`target.file` against a ground-truth case's file suffix-tolerantly (the model may report `discount.py` for
`src/discount.py`). Copy the 3-liner into `testgen.py` (note the origin) exactly as `dedupe.py` did — do not create
a shared util module.

**Constants with `#:` doc-comments citing the FR/TR (mirror `config.py:44–82`).**

**Assert on structure/outcomes, never model wording (PRD principle 5).** Offline tests assert on call counts,
prompt content (diff + existing tests present), and parsed/deduped/skipped structure via monkeypatch. Live tests
assert on outcomes (uncovered case proposed, covered case skipped) via tolerant `case`/keyword matching, never on
the generated code's prose. If the generated `test_code` is checked at all, check only that it is **non-empty and
parses as Python** (`ast.parse`) — a structural property, not content.

**Local imports inside demo drivers (mirror `metrics.run_metrics`/`multipass.run_multipass_demo`):** the live demo
imports `workspace` (and reads fixtures) inside the function, keeping the pure core's import surface minimal.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (verify + schema + fixture + pure cores)
Verify the P1/2/3a spine, add config constants + the one workspace exclusion generalization, author the distinct
test-gen schema, build the fixture (correct function + existing happy-path test + CLAUDE.md testing standards +
diff + answer key), then the pure `testgen.py` functions (`parse_testgen`, `existing_test_names`,
`dedupe_suggestions`, `skip_covered`, `score_testgen`) — all offline-testable before any live call.
**Tasks:** verify interfaces; `config.py`; `workspace.py` glob; `testgen_schema.py`; fixture files; `testgen.py`
pure core + golden output fixture.

### Phase 2: Prompt + live driver (TR1/TR2/TR3/FR2)
The versioned `generate-tests.md` command, then the live `generate_tests` + `run_testgen_demo`.
**Tasks:** `generate-tests.md`; `testgen.py` live driver + demo.

### Phase 3: Integration (Make + emit)
Wire `make test-gen` to the demo; the `emit_tests` helper.
**Tasks:** `Makefile`; `emit_tests`.

### Phase 4: Testing & Validation
Offline unit suite (schema, parse, pure skip/dedupe, orchestration via monkeypatch) + the live acceptance demo +
record results.
**Tasks:** `test_testgen_schema.py`; `test_testgen.py`; `test_testgen_live.py`; run demo; update `_tasks/todo.md`.

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task is atomic and independently testable. `PY=../../.venv/bin/python`; run
from the project root; modules run with `PYTHONPATH=src/review` (see `Makefile:2`).

### VERIFY Phase-1/2/3a interfaces (do this FIRST — do not skip)
- **IMPLEMENT**: Read the ACTUAL `src/review/{config,schema,parse,runner,severity,metrics,dedupe,store,workspace,
  post,multipass,cli}.py` and reconcile names/signatures with "CONTEXT REFERENCES" — especially `Finding` field
  order, `invoke_claude(prompt, schema_json, model, timeout_s, cwd=None)`, `parse_result(stdout) -> ParsedReview`,
  `dedupe.suppress_prior` return shape `(new, still)`, `workspace.staged`/`_EXCLUDE_GLOBS`, `metrics._same_file`,
  `schema.as_json_string`. If anything drifted, adapt the tasks below — **the real code wins.**
- **VALIDATE**:
  ```bash
  ../../.venv/bin/python -m pytest -m "not integration" -q   # expect: 80 passed, 11 deselected (P1+P2+P3a offline green)
  PYTHONPATH=src/review ../../.venv/bin/python -c "import config,schema,parse,runner,severity,metrics,dedupe,store,workspace,post; from parse import Finding,Location; import inspect; print('cwd' in inspect.signature(runner.invoke_claude).parameters, [f for f in Finding.__dataclass_fields__])"
  ```
  → expect `True ['location', 'issue', 'severity', 'suggested_fix', 'detected_pattern', 'category']`

### UPDATE `src/review/config.py` (add Phase-3b test-gen constants)
- **IMPLEMENT**: ADD after the Phase-3a constants (with `#:` doc-comments citing FR2), reusing `PROJECT_ROOT`:
  - `TESTGEN_PROMPT = PROJECT_ROOT / ".claude" / "commands" / "test-gen" / "generate-tests.md"` — the versioned
    test-gen command (FR2; not inlined — mirrors `PROMPT_TEMPLATE`).
  - `TESTGEN_REPO = PROJECT_ROOT / "fixtures" / "testgen-sample"` — the test-gen ground-truth harness (separate
    from `FIXTURE_REPO` so the review precision/TR3 metrics can't be perturbed).
  - `TESTGEN_GROUND_TRUTH = TESTGEN_REPO / "testgen_ground_truth.json"` — the answer key; NEVER staged (excluded by
    the `*ground_truth.json` glob in `workspace.py`).
  - `TESTGEN_DIFF_NAME = "testgen.diff"` — the change-under-test diff filename inside `TESTGEN_REPO`.
  - `TESTGEN_EXISTING_TESTS_NAME = "tests/test_discount.py"` — the existing-tests file (relative to `TESTGEN_REPO`)
    fed into the prompt as coverage context.
- **PATTERN**: `config.py:44–82` (`#:` comments + `PROJECT_ROOT / …` paths). Reuse `METRICS_DIR` (57) for the demo
  output; do NOT add a new metrics dir.
- **IMPORTS**: none new (`Path`, `PROJECT_ROOT` present).
- **GOTCHA**: `TESTGEN_REPO` is a *separate* fixture from `FIXTURE_REPO`. Do not point test-gen at the review
  sample-repo — its files carry seeded bugs and its CLAUDE.md/metrics are calibrated for the review A/B.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import config; print(config.TESTGEN_PROMPT.name, config.TESTGEN_REPO.name, config.TESTGEN_GROUND_TRUTH.name, config.TESTGEN_DIFF_NAME, config.TESTGEN_EXISTING_TESTS_NAME)"`
  → expect `generate-tests.md testgen-sample testgen_ground_truth.json testgen.diff tests/test_discount.py`

### UPDATE `src/review/workspace.py` (generalize the answer-key exclusion glob)
- **IMPLEMENT**: In `_EXCLUDE_GLOBS` (line 33), change the entry `"ground_truth.json"` to `"*ground_truth.json"` so
  BOTH `ground_truth.json` and `testgen_ground_truth.json` are excluded from any staged workspace. Update the
  adjacent `#:` comment to say "answer keys (`*ground_truth.json`)". Leave `STAGE_EXCLUDE` (29) and everything else
  unchanged.
- **PATTERN**: `workspace.py:27–33` (the exclusion constants) + `stage_workspace`'s `shutil.ignore_patterns(*_EXCLUDE_GLOBS)`
  (56) — `ignore_patterns` is fnmatch-based, and `*ground_truth.json` matches the empty prefix, so `ground_truth.json`
  is still excluded (review staging unaffected).
- **IMPORTS**: none.
- **GOTCHA**: This is defense-in-depth (the model must NEVER see any answer key — PRD Risk #3 / workspace docstring
  invariant). Verify the original `ground_truth.json` is STILL excluded (a regression here would leak the review
  answer key). The test in `test_testgen.py` asserts both keys are absent from a staged testgen workspace AND that
  `ground_truth.json` is absent from a staged review workspace.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import fnmatch; print(fnmatch.fnmatch('ground_truth.json','*ground_truth.json'), fnmatch.fnmatch('testgen_ground_truth.json','*ground_truth.json'))"`
  → expect `True True`

### CREATE `src/review/testgen_schema.py` (distinct test-gen output schema — TR2)
- **IMPLEMENT**: Mirror `schema.py`. A module docstring stating this is the *test-gen* contract (distinct from the
  findings contract; top level MUST be an object per `--json-schema`). Define:
  - `TESTGEN_SCHEMA` — top-level object, `required: ["tests"]`, `properties.tests` = array of objects each with
    `required: ["target", "test_name", "case", "description", "test_code"]` and properties:
    - `target`: object, `required: ["file", "symbol"]`, `{file: string, symbol: string}` (the changed
      function/method the test covers).
    - `test_name`: string (a valid pytest function name, e.g. `test_apply_discount_rejects_out_of_range_rate`).
    - `case`: string (a short kebab-case slug naming the behavior under test — the controlled-vocabulary identity
      for dedupe/skip, the test-gen analog of `detected_pattern`, e.g. `rate-out-of-range`).
    - `description`: string (one sentence: the case exercised).
    - `test_code`: string (the complete pytest test function source).
  - `additionalProperties: False` at the top level.
  - `as_json_string() -> str` — `json.dumps(TESTGEN_SCHEMA)` (mirror `schema.as_json_string`).
  - `validate_tests_obj(obj) -> None` — `jsonschema.validate(instance=obj, schema=TESTGEN_SCHEMA)` (mirror
    `schema.validate_findings_obj`; re-validate even though `--json-schema` constrained output — TR2).
- **PATTERN**: `schema.py` (whole file) — same structure, docstrings, `as_json_string`/`validate_*` names.
- **IMPORTS**: `import json`, `import jsonschema`.
- **GOTCHA**: `case` is the controlled slug that makes within-run dedupe deterministic — keep it a required field.
  Do NOT reuse `FINDINGS_SCHEMA` or add a `tests` key to it — this is a separate schema for a separate call.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import testgen_schema as t, json; t.validate_tests_obj({'tests':[{'target':{'file':'src/discount.py','symbol':'apply_discount'},'test_name':'test_x','case':'rate-out-of-range','description':'d','test_code':'def test_x(): pass'}]}); print('ok', json.loads(t.as_json_string())['type'])"`
  → expect `ok object`

### CREATE `fixtures/testgen-sample/src/discount.py` (the change under test — a CORRECT function)
- **IMPLEMENT**: A tiny, correct module with one obvious untested branch:
  ```python
  """Discount pricing helper.

  SEEDED TEST-GEN FIXTURE INTENT: a CORRECT function with a guarded error branch.
  The existing test (tests/test_discount.py) covers ONLY the happy path
  (a valid in-range rate). The uncovered behavior is the ValueError branch
  (rate < 0 or rate > 1) and the boundaries (rate == 0, rate == 1). Test-gen must
  propose a net-new test for the uncovered error path and must NOT re-propose the
  already-covered happy path. There is deliberately NO bug here — test-gen's job
  is coverage, not bug-finding.
  """


  def apply_discount(price, rate):
      """Return ``price`` reduced by ``rate`` (a fraction in [0.0, 1.0])."""
      if rate < 0 or rate > 1:
          raise ValueError("rate must be a fraction in [0.0, 1.0]")
      return price * (1 - rate)
  ```
- **PATTERN**: `fixtures/sample-repo/src/orders.py` (docstring-states-fixture-intent style).
- **GOTCHA**: Keep it correct and self-contained (no imports, no project deps). The untested branch must be
  unambiguous so the "propose the error path" gate is robust on haiku.
- **VALIDATE**: `../../.venv/bin/python -m py_compile fixtures/testgen-sample/src/discount.py && echo OK`

### CREATE `fixtures/testgen-sample/tests/test_discount.py` (existing test — happy path ONLY)
- **IMPLEMENT**: One pytest test covering only the happy path (the "already covered" context):
  ```python
  """Existing tests for discount — HAPPY PATH ONLY (the coverage context for test-gen).

  This file is fed to the test-gen prompt as `{existing_tests}`. It covers the
  in-range (happy) path only; the ValueError / boundary cases are intentionally
  uncovered so test-gen has a clear net-new case to propose and a clear covered
  case to skip. Not collected by the project pytest run (testpaths=tests at repo root).
  """

  from discount import apply_discount


  def test_apply_discount_basic():
      assert apply_discount(100, 0.1) == 90
  ```
- **PATTERN**: minimal pytest; import style mirrors the fixture being self-contained.
- **GOTCHA**: The project `pytest.ini` has `testpaths = tests` (repo root), so this fixture test is NOT collected
  by `make test` — confirm by running the offline suite after adding it (count must not change except for the new
  `tests/test_testgen*.py`). Do NOT add `fixtures/` to `testpaths`.
- **VALIDATE**: `../../.venv/bin/python -m py_compile fixtures/testgen-sample/tests/test_discount.py && echo OK`

### CREATE `fixtures/testgen-sample/testgen.diff` (the unified diff of the change under test)
- **IMPLEMENT**: A unified diff adding `src/discount.py` (the new-file form, mirroring `pr.diff`'s per-file chunk):
  ```diff
  diff --git a/src/discount.py b/src/discount.py
  new file mode 100644
  --- /dev/null
  +++ b/src/discount.py
  @@ -0,0 +1,18 @@
  +"""Discount pricing helper.
  +... (the full discount.py content as + lines, matching the file exactly) ...
  +    return price * (1 - rate)
  ```
  The `+` lines MUST reproduce `discount.py` verbatim; the `@@ -0,0 +1,N @@` count MUST equal the file's line count.
- **PATTERN**: `fixtures/sample-repo/pr.diff` (whole file) — exact header/hunk format.
- **GOTCHA**: `testgen.diff` matches the `*.diff` exclusion glob, so it is NOT staged into the workspace (good — the
  diff goes into the prompt, not the tree). Keep the hunk line count correct or the model may mis-number
  `target`/line context (not asserted on, but keep it clean).
- **VALIDATE**: `grep -c '^+' fixtures/testgen-sample/testgen.diff` (sanity: matches the file's line count + no
  surprises); `test -f fixtures/testgen-sample/testgen.diff && echo OK`

### CREATE `fixtures/testgen-sample/CLAUDE.md` (testing standards — the test-gen TR3 context channel)
- **IMPLEMENT**: A reviewed-project CLAUDE.md carrying **testing standards** (not review policy). Mirror the
  `fixtures/sample-repo/CLAUDE.md` framing (a note that this is the reviewed project's runtime context channel, not
  bot-dev guidance), then a "Testing standards" section, e.g.: use `pytest`; one behavior per test; name tests
  `test_<function>_<behavior>`; cover error/edge paths with `pytest.raises`; do not duplicate an existing test's
  case. This is what `claude -p` auto-loads from `cwd` for the test-gen pass (TR3).
- **PATTERN**: `fixtures/sample-repo/CLAUDE.md` (whole file) — the header note + authoritative-conventions sections.
- **GOTCHA**: This is the SECOND reviewed-project CLAUDE.md (test-gen's TR3 channel). It is NOT this repo's bot-dev
  CLAUDE.md and NOT the review sample-repo's. Keep it scoped to testing standards.
- **VALIDATE**: `grep -qi 'test' fixtures/testgen-sample/CLAUDE.md && echo OK`

### CREATE `fixtures/testgen-sample/testgen_ground_truth.json` (the answer key)
- **IMPLEMENT**: A `cases` array. Each case: a stable `id`/`case` slug, a `should_propose` boolean, a `keywords`
  list (for tolerant matching against model-generated slugs/descriptions — structure, not prose), and a `note`:
  ```json
  {
    "diff": "testgen.diff",
    "existing_tests": "tests/test_discount.py",
    "target": {"file": "src/discount.py", "symbol": "apply_discount"},
    "note": "Answer key for test-gen. NEVER staged (workspace excludes *ground_truth.json).",
    "cases": [
      {"id": "happy-path", "should_propose": false,
       "keywords": ["basic", "happy", "valid", "in-range", "in range", "applies discount"],
       "note": "Already covered by existing test_apply_discount_basic — must be SKIPPED, not re-proposed."},
      {"id": "rate-out-of-range", "should_propose": true,
       "keywords": ["out-of-range", "out of range", "valueerror", "raises", "invalid", "> 1", "< 0", "negative"],
       "note": "The ValueError branch (rate<0 or rate>1) is uncovered — test-gen MUST propose it (net-new)."},
      {"id": "rate-boundary", "should_propose": true, "optional": true,
       "keywords": ["boundary", "zero", "rate 0", "rate 1", "1.0", "0.0", "edge"],
       "note": "rate==0 / rate==1 boundaries; bonus net-new case, not a hard gate."}
    ]
  }
  ```
- **PATTERN**: `fixtures/sample-repo/ground_truth.json` (the `cases`-array + per-case dict + `note` shape).
- **GOTCHA**: `keywords` exist because the model GENERATES the `case` slug and `description` (nondeterministic
  wording) — matching on keyword presence is the structural-ish signal, mirroring how the review live tests assert
  direction/outcomes not prose. The hard gates are `happy-path` (should_propose:false) and `rate-out-of-range`
  (should_propose:true); `rate-boundary` is `optional` (recorded, not asserted). Filename ends `ground_truth.json`
  so the `*ground_truth.json` glob excludes it from staging.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import json,config; d=json.loads(config.TESTGEN_GROUND_TRUTH.read_text()); print(len(d['cases']), [c['id'] for c in d['cases']])"`
  → expect `3 ['happy-path', 'rate-out-of-range', 'rate-boundary']`

### CREATE `src/review/testgen.py` — pure core (parse + skip/dedupe + score; offline)
- **IMPLEMENT**: Module docstring (mirror `dedupe.py`) describing the pure/live split and the two-layer FR2 skip.
  At the top import stdlib + `testgen_schema` for the pure part; import `runner`, `config`, `workspace` refs used
  by the live driver at module top too (none touch the CLI at import — enables monkeypatch). Define:
  - `@dataclass Target: file: str; symbol: str`.
  - `@dataclass TestSuggestion: target: Target; test_name: str; case: str; description: str; test_code: str`.
  - `@dataclass ParsedTestGen: tests: list; is_error: bool; terminal_reason: "str | None"; raw: list`.
  - `class TestGenParseError(Exception)` — OR reuse `parse.ParseError` (prefer reusing `from parse import ParseError`
    to keep one error type; note the reuse in a comment). **Decide: reuse `parse.ParseError`** (fewer types; it is
    generic enough — "CLI stdout cannot be parsed").
  - `parse_testgen(stdout: str) -> ParsedTestGen` — MIRROR `parse.parse_result` verbatim in shape (json.loads →
    non-empty list check → find `type=="result"` elem → `is_error` short-circuit → prefer `structured_output`,
    fall back to `json.loads(result_elem["result"])` → `testgen_schema.validate_tests_obj(payload)` → build
    `TestSuggestion`s from `payload["tests"]`). Raise `ParseError` (imported) on unparseable/empty/no-result.
    Note in a comment that the event-locating logic mirrors `parse.parse_result` (copied, not shared, per house
    pattern).
  - `_same_file(a, b) -> bool` — copy verbatim from `metrics._same_file` (note origin).
  - `existing_test_names(source: str) -> "set[str]"` — regex-extract pytest test function names:
    `re.findall(r"^\s*def (test_\w+)\s*\(", source, re.MULTILINE)` → a set. Pure, never raises (empty/malformed →
    `set()`).
  - `dedupe_suggestions(suggestions: "list[TestSuggestion]") -> "list[TestSuggestion]"` — within-run collapse:
    keep the FIRST suggestion per `case` slug (normalized: `case.strip().lower()`); empty-slug suggestions are all
    kept (can't dedupe an unnamed case — mirror `dedupe.is_duplicate`'s empty-pattern fallback rationale). Stable,
    pure, returns a new list.
  - `skip_covered(suggestions, existing_names: "set[str]") -> "tuple[list, list]"` — return `(new, skipped)`
    mirroring `dedupe.suppress_prior`'s `(new, still)`: a suggestion is `skipped` if its `test_name` (normalized:
    `strip().lower()`) is already in `existing_names` (normalized the same way); else `new`. This is the
    deterministic backstop — the FR2 "never re-emit a covered test" guarantee. Pure, never raises, never mutates.
  - `@dataclass TestGenResult: proposed: list; skipped_covered: list; matched: list; missing_required: list;
    unexpected: list` (case ids), and `score_testgen(suggestions, cases) -> TestGenResult` — pure scorer:
    - `_covers(s, case)` = any keyword in `case["keywords"]` appears in
      `f"{s.case} {s.description} {s.test_name}".lower()`.
    - `matched` = ids of `should_propose:true` cases covered by some suggestion.
    - `missing_required` = ids of `should_propose:true` non-optional cases NOT covered (the hard-gate misses).
    - `unexpected` = ids of `should_propose:false` cases that WERE covered (a covered case re-proposed — the FR2
      failure). Record but do not raise.
- **PATTERN**: `parse.py` (parser shape), `dedupe.py` (pure `(new, still)` split + keep-first + empty-slug
  fallback), `metrics.py` (`_same_file`, `MetricsResult` dataclass + `score` shape).
- **IMPORTS**: `import json, re`; `from dataclasses import dataclass`; `import testgen_schema`; `from parse import
  ParseError`. (Live-driver adds `import config, runner, workspace` — safe at top; none call the CLI at import.)
- **GOTCHA**: (1) Match/skip identity is the controlled `case` slug (within-run) and `test_name` collision
  (vs existing) — NEVER the `description`/`test_code` prose (reworded every run → nondeterministic). (2)
  `skip_covered` by name-collision is the DETERMINISTIC backstop; the PRIMARY skip is the prompt-context layer (the
  model reading existing tests) — document this honestly (a suggestion that covers the same behavior under a
  *different* name is caught by the prompt layer, not the structural key — mirror the Phase-3a cross-end dedupe
  honesty note). (3) `existing_test_names` must handle indented methods and decorators gracefully (the
  `^\s*def test_…` regex with `re.MULTILINE` does).
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import testgen as T; print(sorted(T.existing_test_names('def test_a():\n    pass\n\ndef test_b():\n    pass\ndef helper(): pass')))"`
  → expect `['test_a', 'test_b']`

### CREATE `tests/fixtures/sample_testgen_output.json` (recorded golden test-gen CLI output)
- **IMPLEMENT**: A minimal valid CLI event array (mirror `tests/fixtures/sample_claude_output.json`): a `system`
  init event + a `result` event with `is_error: false`, `terminal_reason: "completed"`, BOTH a `result` JSON
  string AND a `structured_output` object holding `{"tests":[{ target, test_name, case, description, test_code }]}`
  — e.g. one suggestion for `case: "rate-out-of-range"` targeting `src/discount.py`/`apply_discount` with a
  `test_code` like `import pytest\nfrom discount import apply_discount\n\ndef test_apply_discount_rejects_out_of_range():\n    with pytest.raises(ValueError):\n        apply_discount(100, 2)`.
- **PATTERN**: `tests/fixtures/sample_claude_output.json` (whole file) — same event shapes, both payload forms.
- **GOTCHA**: Keep both `result` (string) and `structured_output` (object) so the parse test can exercise the
  primary path AND the fallback (delete `structured_output` in a copy within the test to hit the fallback, as
  `test_parse.py` does).
- **VALIDATE**: `../../.venv/bin/python -c "import json; d=json.load(open('tests/fixtures/sample_testgen_output.json')); r=[e for e in d if e['type']=='result'][0]; print('tests' in r['structured_output'])"`
  → expect `True`

### CREATE `.claude/commands/test-gen/generate-tests.md` (the versioned test-gen prompt — FR2/TR2/TR3)
- **IMPLEMENT**: A versioned command (frontmatter `---\ndescription: Generate net-new tests for a change, skipping
  covered cases\n---`). Mirror `review-diff.md`'s structure. Contents:
  - Role: "You generate **net-new** pytest tests for a single code change supplied as a unified diff. You are given
    the project's **existing tests** for this code. Propose tests ONLY for behaviors the existing tests do NOT
    already cover — re-proposing a covered case is noise and gets the tool muted."
  - Honor the project `CLAUDE.md` testing standards (loaded automatically from the working directory) — same TR3
    respect clause as `review-diff.md:10–13`.
  - Emit every test ONLY through structured output — never prose. If every meaningful behavior is already covered,
    return an empty `tests` array.
  - **PROPOSE a test only when** it exercises a behavior of the changed code NOT covered by the existing tests:
    an untested error/exception path, an uncovered branch, an unhandled edge/boundary, a distinct valid-input class.
  - **DON'T propose**: a test whose behavior an existing test already covers (even if you'd name it differently);
    trivial/tautological tests; tests for unchanged code; tests that merely restate the happy path.
  - **One few-shot pair (TR4 discipline):** *No test* — the existing `test_apply_discount_basic` already covers a
    valid in-range rate → do NOT propose another happy-path test. *Test* — no existing test exercises an
    out-of-range `rate`; propose `case: rate-out-of-range` asserting `pytest.raises(ValueError)`. (Teaches the
    covered-vs-uncovered discrimination; the fixture is the same class, not a memorized answer.)
  - **Field guidance** (aligned to `TESTGEN_SCHEMA`): `target.file` = the path after `+++ b/`; `target.symbol` =
    the changed function/method; `test_name` = a valid pytest name `test_<symbol>_<behavior>`; `case` = a short
    kebab-case slug naming the behavior (e.g. `rate-out-of-range`) — the dedupe identity; `description` = one
    sentence; `test_code` = a complete, runnable pytest function (imports + `def test_…`).
  - End with BOTH placeholder blocks: the change under review as ` ```diff\n{diff}\n``` ` and the existing tests as
    ` ```python\n{existing_tests}\n``` `.
- **PATTERN**: `review-diff.md` (whole file) — frontmatter, honor-CLAUDE.md clause, emit-only rule, few-shot format,
  field guidance, fenced placeholder tail. Change the task (generate tests, skip covered) + add the second block.
- **GOTCHA**: The prompt text is NEVER asserted on (validation is structural) — refine wording freely to make haiku
  reliably (a) propose the out-of-range case and (b) skip the happy path. The `{existing_tests}` placeholder is the
  prompt-context skip layer (the primary FR2 mechanism). Use `.replace()` not `.format()` in the driver (diffs +
  code contain `{`/`}`).
- **VALIDATE**: `grep -q '{diff}' .claude/commands/test-gen/generate-tests.md && grep -q '{existing_tests}' .claude/commands/test-gen/generate-tests.md && echo OK`

### CREATE `src/review/testgen.py` — live driver + emit + demo (TR1/TR2/TR3/FR2)
- **IMPLEMENT**: Below the pure core, the live orchestrator (mirror `metrics.run_variant`/`multipass._run_pass`):
  - `_strip_frontmatter(text) -> str` — copy the 6-line frontmatter strip (as `metrics`/`multipass`/`cli` each do).
  - `_load_template(prompt_path) -> str` — read + strip a versioned prompt file.
  - `generate_tests(diff_text, existing_tests_text, *, prompt_path=None, model, cwd=None) -> "list[TestSuggestion]"`
    — `prompt_path = prompt_path or config.TESTGEN_PROMPT`; `template = _load_template(prompt_path)`;
    `prompt = template.replace("{diff}", diff_text).replace("{existing_tests}", existing_tests_text)`;
    `result = runner.invoke_claude(prompt, testgen_schema.as_json_string(), model, config.CLAUDE_TIMEOUT_S, cwd=cwd)`;
    `parsed = parse_testgen(result.stdout)`; return `[]` if `parsed.is_error` else `dedupe_suggestions(parsed.tests)`.
    (ONE fresh `claude -p` call — TR1/TR7; tolerant of an error review → `[]`.)
  - `format_test(t: TestSuggestion) -> str` and `emit_tests(tests) -> None` — mirror `post.format_comment`/`emit`:
    print a count header (`f"{len(tests)} proposed test(s)"`) then per test a header line
    (`f"{t.target.file}::{t.test_name} [{t.case}] {t.description}"`) followed by the indented `test_code`.
  - `run_testgen_demo() -> dict` (`make test-gen`; LIVE) — mirror `metrics.run_metrics`/`multipass.run_multipass_demo`:
    local `import workspace, json`; read `diff = (config.TESTGEN_REPO / config.TESTGEN_DIFF_NAME).read_text()` and
    `existing = (config.TESTGEN_REPO / config.TESTGEN_EXISTING_TESTS_NAME).read_text()`; stage the fixture once
    (`workspace.staged(config.TESTGEN_REPO, include_claude_md=True)`), run `generate_tests(diff, existing,
    model=config.BASELINE_MODEL, cwd=str(ws))`; compute `existing_names = existing_test_names(existing)`;
    `new, skipped = skip_covered(suggestions, existing_names)`; load `cases = json.loads(
    config.TESTGEN_GROUND_TRUTH.read_text())["cases"]`; `result = score_testgen(new, cases)`; `emit_tests(new)`;
    print the headline (`proposed net-new: len(new)`, `skipped (already covered): len(skipped)`,
    `covered case re-proposed (should be 0): len(result.unexpected)`, `uncovered error-path proposed:
    'rate-out-of-range' in result.matched`); write `data/metrics/testgen.json` (mirror `_write_metrics`:
    `METRICS_DIR.mkdir(...)`, `json.dumps({...}, indent=2)`). Return a dict.
- **PATTERN**: `metrics.run_variant` (188–222) staged→invoke→parse shape; `metrics._write_metrics` (232–251)
  write-json; `multipass.run_multipass_demo` (232–285) demo-driver + print + write shape; `post.emit` (25–29).
- **IMPORTS**: top: `import json, re`, `from dataclasses import dataclass`, `import testgen_schema`, `import config,
  runner`, `from parse import ParseError`. Inside `run_testgen_demo`: `import workspace` (and `json` already top).
- **GOTCHA**: (1) `.replace()` for BOTH placeholders (diff + code have braces). (2) ONE `invoke_claude` call — no
  multi-pass. (3) `skip_covered` runs in the DRIVER (the pure `generate_tests` only within-run dedupes) — so tests
  can exercise each layer separately, mirroring how `cli.py` applies `dedupe.suppress_prior` around
  `multipass.review_multipass`. (4) Emit-only — NO `gh`. (5) Wrap nothing extra: `invoke_claude` already has the
  timeout backstop; the demo is a script, not the CLI, so a raised `TimeoutExpired` surfacing is acceptable there.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import testgen, inspect; print([n for n in ('parse_testgen','existing_test_names','dedupe_suggestions','skip_covered','score_testgen','generate_tests','emit_tests','run_testgen_demo') if hasattr(testgen,n)]); print('cwd' in inspect.signature(testgen.generate_tests).parameters)"`
  → expect all eight names + `True`

### UPDATE `Makefile` (wire the `test-gen` stub to the demo driver)
- **IMPLEMENT**: Replace the `test-gen` stub recipe (lines 22–23) with:
  ```make
  # test-gen makes a LIVE claude -p call (needs CLI + ANTHROPIC_API_KEY; haiku
  # tier). Generates net-new tests for the testgen fixture change and skips
  # already-covered cases (FR2). NOT run by `make test`.
  test-gen:
  	PYTHONPATH=$(PYTHONPATH) $(PY) -c "import testgen; testgen.run_testgen_demo()"
  ```
  `test-gen` is already in `.PHONY` (line 4) — leave it. Remove the old "not implemented (Phase 3)" comment/echo.
- **PATTERN**: `Makefile:28–42` (`metrics`/`review-multi` targets + LIVE-call comment + `$(PY) -c "import X; X.f()"`).
- **GOTCHA**: TABS not spaces in the recipe. Do not add a `PR=` arg — the demo is fixture-driven (like
  `review-multi`/`metrics`, which take no PR). A generic `--diff/--existing-tests` CLI is a documented follow-up,
  not MVP (see NOTES).
- **VALIDATE**: `make -n test-gen` → prints the `$(PY) -c "import testgen; testgen.run_testgen_demo()"` line.

### CREATE `tests/test_testgen_schema.py` (OFFLINE — TR2)
- **IMPLEMENT**: Mirror `test_schema.py`: a valid `{"tests":[…]}` object passes `validate_tests_obj`; a missing
  required field (drop `case` or `target`) raises `jsonschema.ValidationError`; a wrong type (e.g. `target` a
  string) raises; `as_json_string()` round-trips (`json.loads(as_json_string())["type"] == "object"` and
  `["required"] == ["tests"]`); `additionalProperties` False at top level rejects an extra top-level key.
- **PATTERN**: `tests/test_schema.py` (whole file).
- **IMPORTS**: `import pytest, json, jsonschema, testgen_schema`.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_testgen_schema.py -q`

### CREATE `tests/test_testgen.py` (OFFLINE — parse + pure skip/dedupe + score + orchestration via monkeypatch)
- **IMPLEMENT**: No live calls. Sections:
  - **parse_testgen** (mirror `test_parse.py`): read `tests/fixtures/sample_testgen_output.json` → one
    `TestSuggestion` with the right `target.file`/`case`; an `is_error:true` result → `tests==[]`, `is_error True`;
    delete `structured_output` from a copy → still parses via the `result` string fallback; malformed stdout
    (`"not json"`) → `ParseError`.
  - **existing_test_names**: a source with two `test_…` defs + a non-test `def helper` → `{"test_a","test_b"}`;
    empty string → `set()`; indented method `    def test_method(self):` → included.
  - **dedupe_suggestions**: two suggestions with the same `case` slug → collapse to one (keep-first, stable);
    distinct slugs → both kept; empty-slug suggestions → all kept.
  - **skip_covered (the FR2 backstop, headline)**: existing_names `{"test_apply_discount_basic"}`; suggestions =
    [a happy-path suggestion named `test_apply_discount_basic` (collides), an error-path suggestion named
    `test_apply_discount_rejects_out_of_range`]; assert `new == [error-path]` and `skipped == [happy-path]` →
    **a covered test is never re-emitted**; case-insensitive collision (`Test_Apply_Discount_Basic` still skipped);
    no mutation of inputs.
  - **score_testgen**: given `new` covering `rate-out-of-range` and cases from the fixture answer key →
    `matched` contains `rate-out-of-range`, `missing_required` empty, `unexpected` empty; a suggestion covering the
    happy-path keywords when `happy-path.should_propose==false` → `unexpected` contains `happy-path`.
  - **orchestration via monkeypatch (mirror `test_multipass._make_fake`)**: a `fake_invoke(prompt, schema_json,
    model, timeout_s, cwd=None)` returning a canned `runner.RunResult` (valid event array with one test
    suggestion), appended to a `calls` list; `monkeypatch.setattr(testgen.runner, "invoke_claude", fake)`;
    `generate_tests(diff_text, existing_text, model="haiku")` calls `invoke_claude` **exactly once**; assert BOTH
    the diff marker (`"discount"`) AND the existing-tests marker (`"test_apply_discount_basic"`) are present in the
    single call's prompt (proves both blocks are substituted); the returned suggestions equal the canned parse.
  - Local `_suggestion(...)` builder helper (mirror `test_dedupe._f`).
- **PATTERN**: `test_multipass.py` (monkeypatch harness + call-count/prompt-content asserts), `test_dedupe.py`
  (pure builder + structural asserts), `test_parse.py` (golden + fallback + malformed).
- **IMPORTS**: `import json, pytest, config, testgen, runner; from parse import ParseError`.
- **GOTCHA**: Monkeypatch `testgen.runner.invoke_claude` (the name `testgen` resolved at import), not
  `runner.invoke_claude` globally. The fake returns a `runner.RunResult` so `parse_testgen(result.stdout)` works.
  No `claude` CLI / key needed → runs under `-m "not integration"`.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_testgen.py -q`

### CREATE `tests/test_testgen_live.py` [integration] (FR2 acceptance)
- **IMPLEMENT**: `pytestmark = [pytest.mark.integration, pytest.mark.skipif(shutil.which("claude") is None, …)]`
  (mirror `test_precision_live.py:21–27`), `model=config.BASELINE_MODEL` (haiku). Read the fixture diff + existing
  tests; stage `config.TESTGEN_REPO` (CLAUDE.md present) and pass `cwd`. Tests:
  1. **Proposes the uncovered error path (FR2):** `suggestions = generate_tests(diff, existing, model=…, cwd=…)`;
     `result = score_testgen(suggestions, cases)`; assert `"rate-out-of-range" in result.matched` (the ValueError
     branch is proposed). (Tolerant keyword match — never asserts prose.)
  2. **Skips the already-covered happy path (FR2 headline):** `new, skipped = skip_covered(suggestions,
     existing_test_names(existing))`; `result2 = score_testgen(new, cases)`; assert `"happy-path" not in
     result2.matched` and `result2.unexpected == []` → **no already-covered test is proposed** (PRD §5 story 6 /
     §11 gate). (The prompt layer should already skip it; `skip_covered` is the backstop.)
  3. **(structural, best-effort) generated test code is real Python:** for each proposed suggestion, assert
     `ast.parse(t.test_code)` does not raise AND `t.test_code.strip()` is non-empty. If haiku emits occasionally
     non-parseable code, this is the one to relax to "non-empty" with a documented note — never loosen #1/#2.
- **PATTERN**: `test_precision_live.py` (whole file) — integration gating, `score`/match usage, assert-on-outcomes.
- **GOTCHA**: These calls cost money and are non-deterministic. #1 (propose the obvious uncovered ValueError branch)
  and #2 (skip the single covered happy path) are robust on haiku given the unambiguous fixture; if #1 is flaky,
  iterate `generate-tests.md` wording or run on `config.REVIEW_MODEL` (sonnet) as a documented fallback — NEVER
  loosen the assert to make a weak prompt pass. #2's determinism also lives in `test_testgen.py`'s `skip_covered`
  test; the live version proves the real run produces a skippable covered case.
- **VALIDATE**:
  ```bash
  export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
  ../../.venv/bin/python -m pytest -m integration tests/test_testgen_live.py -q
  ```

### UPDATE `_tasks/todo.md`
- **IMPLEMENT**: Add a "Phase 3b — Test Generation (FR2)" checklist mirroring these tasks; mark complete as you go;
  append a review section (what worked / what didn't / recorded results: did haiku propose the uncovered error-path
  case? did it skip the covered happy path? any prompt calibration needed? was the ast.parse check kept or relaxed?).
  Note TR9/FR4 quarantine + `gh --post` remain Phase 4.
- **VALIDATE**: `test -f _tasks/todo.md`

---

## TESTING STRATEGY

### Unit Tests (offline, default `-m "not integration"` — MUST pass with zero network/CLI)
- **testgen_schema** (`test_testgen_schema.py`): schema validity, enum/required/type enforcement, top-level
  `additionalProperties:false`, round-trip.
- **testgen** (`test_testgen.py`): `parse_testgen` (golden → suggestion, is_error, structured_output vs result
  fallback, malformed → ParseError); `existing_test_names` extraction; `dedupe_suggestions` within-run collapse;
  `skip_covered` — the **"a covered test is never re-emitted"** deterministic guarantee (the FR2 headline);
  `score_testgen`; **orchestration via monkeypatched `invoke_claude`** — exactly ONE call, prompt carries both the
  diff and the existing tests, returns the parsed suggestions. No live model — deterministic.
- All: assertions on structure/constants; **never on model wording** (PRD principle 5).

### Integration Tests (`-m integration`, gated on `claude_runnable()`, haiku tier)
- **testgen-live** (`test_testgen_live.py`): the two FR2 acceptance demos — proposes the uncovered error-path case;
  skips the already-covered happy path (zero re-proposed covered tests) — plus a best-effort "generated code
  parses" structural check.

### Edge Cases (must be covered)
- Empty `existing_tests` (no coverage yet) → `existing_test_names` returns `set()`; `skip_covered` skips nothing
  (everything is net-new).
- Every behavior already covered → the model returns an empty `tests` array → `generate_tests` returns `[]`
  gracefully (no crash); `emit_tests([])` prints `0 proposed test(s)`.
- One `is_error` review envelope → `generate_tests` returns `[]` (one bad run ≠ crash), mirroring `_run_pass`.
- Suggestion with an empty `case` slug → `dedupe_suggestions` keeps it (can't dedupe an unnamed case).
- Case-insensitive test-name collision (`Test_Apply_Discount_Basic` vs `test_apply_discount_basic`) → still skipped.
- Model reports `target.file` as `discount.py` vs ground-truth `src/discount.py` → `score_testgen._same_file`
  suffix-matches.
- The testgen answer key is NEVER staged (`*ground_truth.json` excluded) AND the review `ground_truth.json` is
  STILL excluded (no regression) — assert both by staging each fixture and checking the file's absence.

---

## VALIDATION COMMANDS

Run from the project root (`.../projects/claude-code-ci-review-bot`). `PY=../../.venv/bin/python`.

### Level 1: Syntax & Style
```bash
../../.venv/bin/python -m py_compile src/review/*.py tests/*.py \
  fixtures/testgen-sample/src/*.py fixtures/testgen-sample/tests/*.py
# (no ruff/black in the shared venv — py_compile is the syntax gate, per Phase 1/2/3a)
```

### Level 2: Unit Tests (offline — MUST pass with zero network/CLI; includes all P1/P2/P3a tests)
```bash
../../.venv/bin/python -m pytest -m "not integration" -q
# EXPECT: previous 80 + new offline tests (test_testgen_schema + test_testgen), all passing; 0 requiring CLI/network.
```

### Level 3: Integration Tests (needs `claude` CLI + ANTHROPIC_API_KEY; haiku cost, ONE call per generate)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
../../.venv/bin/python -m pytest -m integration tests/test_testgen_live.py -q
```

### Level 4: Manual Validation (the headline deliverable)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
make test-gen   # generates net-new tests for the testgen fixture; prints:
                #   proposed net-new: N ; skipped (already covered): M
                #   covered case re-proposed (should be 0): 0
                #   uncovered error-path proposed: True
```
EXPECT: a proposed test for the out-of-range `ValueError` case; the happy path NOT re-proposed; `testgen.json`
written under `data/metrics/`.

### Level 5: Additional Validation (regression — Phase-1/2/3a behavior preserved)
```bash
# Review default path unchanged (workspace exclusion generalization must not affect review staging):
make ci-review PR=fixtures/pr-01/sample.diff < /dev/null; echo "exit: $?"     # exit 0, 1 finding
# The review answer key is STILL excluded from a staged review workspace:
PYTHONPATH=src/review ../../.venv/bin/python -c "import config, workspace; \
  ws=workspace.stage_workspace(config.FIXTURE_REPO, True); import pathlib; \
  print('ground_truth staged:', (pathlib.Path(ws)/'ground_truth.json').exists()); \
  workspace.cleanup_workspace(ws)"                                            # expect: ground_truth staged: False
```

---

## ACCEPTANCE CRITERIA

- [ ] **FR2 net-new:** on the fixture, test-gen proposes a test for the **uncovered** out-of-range (`ValueError`)
      behavior of `apply_discount` (`"rate-out-of-range" in score_testgen(...).matched`).
- [ ] **FR2 skip-covered (headline):** test-gen does **NOT** re-propose the already-covered happy path — proven
      deterministically offline (`skip_covered` splits a colliding suggestion into `skipped`, the covered case is
      never in `new`) AND live (`score_testgen(new).unexpected == []`, `"happy-path" not in matched`).
- [ ] **TR2:** 100% of proposed tests validate against `TESTGEN_SCHEMA` (distinct from `FINDINGS_SCHEMA`); the
      schema drives both `--json-schema` and post-hoc validation.
- [ ] **TR1:** test-gen runs headless via `claude -p` (one non-interactive call, timeout backstop) — no hang.
- [ ] **TR3:** the test-gen run loads `fixtures/testgen-sample/CLAUDE.md` (testing standards) from the staged cwd.
- [ ] **Two-layer skip:** prompt-context layer (existing tests fed in) + deterministic `skip_covered` backstop,
      mirroring Phase-3a dedupe.
- [ ] **Regression:** `make ci-review PR=fixtures/pr-01/sample.diff` and ALL Phase-1/2/3a tests pass **unchanged**;
      the review `ground_truth.json` is still excluded from review staging (the `*ground_truth.json` glob change is
      non-regressive).
- [ ] Offline unit suite (`-m "not integration"`) passes with **no network/CLI**; integration suite passes when the
      CLI is available (skips cleanly otherwise).
- [ ] No `claude-agent-sdk` / `anthropic` / `gh` imports (CLI-as-agent; posting is Phase 4).
- [ ] No answer key ever reaches the model (`testgen_ground_truth.json` excluded from staging; `testgen.diff`
      excluded by `*.diff`).

---

## COMPLETION CHECKLIST
- [ ] Phase 1/2/3a verified present & green BEFORE starting; interfaces reconciled with the real code.
- [ ] All tasks completed in order; each task's `VALIDATE` passed immediately.
- [ ] Level 1–4 validation executed; `make test-gen` produces the demonstrable result (uncovered case proposed,
      covered case skipped, zero re-proposed covered tests).
- [ ] Level 5 regression confirmed: review default path + all P1/P2/P3a tests unchanged; review answer key still
      excluded.
- [ ] Offline unit suite green; integration suite green (or cleanly skipped).
- [ ] No linting/type errors (`py_compile` clean, incl. the fixture Python files).
- [ ] `_tasks/todo.md` updated with a completion review (incl. whether haiku proposed the uncovered case and
      skipped the covered one, and any prompt calibration / ast.parse-check decision).

---

## NOTES

**Decisions made during planning (with rationale):**

1. **Test-gen modules live in `src/review/`, not a new `src/testgen/` package** — a deliberate deviation from the
   PRD §6 *proposed* directory diagram (`src/testgen/generate.py`). The actual codebase collapsed everything under
   `src/review/` with a single flat `PYTHONPATH=src/review` and flat imports (`import config`, `from parse import
   Finding`); a separate `src/testgen/` package would break those imports and the single PYTHONPATH. The real code
   is ground truth (CLAUDE.md), and the PRD diagram was a proposal (it also listed `src/review/instrument.py` etc.
   that the code reorganized). Files: `testgen_schema.py` (sibling to `schema.py`), `testgen.py` (bundles the
   pure/live split like `metrics.py`/`multipass.py`).

2. **A distinct schema + a mirrored-not-shared parser.** `TESTGEN_SCHEMA` is a second canonical contract (a `tests`
   array), and `parse_testgen` duplicates `parse.parse_result`'s ~15-line event-locating shape rather than
   refactoring `parse.py`. This follows the established house pattern (`dedupe._same_file` copied from
   `metrics._same_file`; `_strip_frontmatter` copied in three modules) and the plan's cardinal rule: do NOT reshape
   the Phase-1/2/3a review contract. `parse.ParseError` is reused (one error type).

3. **The FR2 skip is two-layer, mirroring the proven Phase-3a dedupe design.** Prompt-context layer (existing test
   bodies fed into `{existing_tests}` → the model skips covered behaviors — the *semantic* layer that catches a
   covered case even under a different test name) + deterministic structural backstop (`skip_covered` by test-name
   collision + `dedupe_suggestions` by `case` slug — the *offline-testable guarantee*). This is intentional
   symmetry with `dedupe.py`'s prompt-context + structural layers. **Honest limitation (documented, mirroring the
   Phase-3a cross-end dedupe note):** the structural backstop keys on `test_name` collision, so a re-proposed
   covered case under a *different* name is caught only by the prompt layer, not the structural key — the offline
   test proves the deterministic backstop; the live test proves the semantic layer on the real model.

4. **A separate `fixtures/testgen-sample/` fixture, not the review sample-repo.** The review fixture's files carry
   seeded bugs and its `CLAUDE.md`/`ground_truth.json` are calibrated for the precision/TR3 A/B — reusing it risks
   perturbing the headline review metric. Test-gen needs a **correct** function with an unambiguous untested branch
   (coverage, not bug-finding), and its own `CLAUDE.md` (testing standards) cleanly demonstrates TR3 for the
   test-gen path. Cost: a second reviewed-project CLAUDE.md (honest — it's a second reviewed project).

5. **One-line `workspace._EXCLUDE_GLOBS` generalization (`"ground_truth.json"` → `"*ground_truth.json"`).** Ensures
   the new `testgen_ground_truth.json` answer key is never staged (defense-in-depth — the model must never see any
   answer key, workspace docstring invariant / PRD Risk #3). The glob still matches the original `ground_truth.json`
   (fnmatch `*` matches empty prefix), so review staging is byte-for-byte unaffected — asserted by a regression test.

6. **`make test-gen` is the fixture demo (no `PR=` arg), matching the sibling live-demo targets** (`metrics`,
   `tr3-demo`, `review-multi`, `dedupe-demo` all take no PR arg and run the fixture). The PRD §10 `make test-gen
   PR=<path>` generic form is a documented **follow-up**, not MVP: a generic CLI needs a way to pass the
   existing-tests path (`--existing-tests`) and to locate the project's tests for an arbitrary diff — real scope
   beyond the FR2 fixture proof. Keeping the demo fixture-driven matches the actual codebase convention and keeps
   Phase 3b tight.

7. **Test-gen does NOT persist suggestions across runs (no `store.py` addition).** The re-run duplicate-suppression
   loop (TR8) is a review concern; for test-gen the **existing tests file IS the "prior"** — coverage is defined by
   what's already tested, not by what was suggested last run. So Phase 3b reuses `store`'s write-json *idiom* (via
   `metrics._write_metrics`) for the demo output only, and adds nothing to `store.py`.

8. **Scoring is behavioral + keyword-tolerant, not precision/recall.** The review headline metric is precision/
   recall on seeded bugs; test-gen's acceptance is the binary FR2 behavior (uncovered case proposed, covered case
   skipped). Because the model *generates* the `case` slug/description (nondeterministic wording), `score_testgen`
   matches via keyword presence (structure-ish), and the hard gates are `rate-out-of-range` (proposed) +
   `happy-path` (skipped). `rate-boundary` is `optional` — recorded, not asserted — so a stricter model isn't
   penalized and a lazier one isn't failed on a bonus case.

**Prerequisites & environment gotchas:**
- Phases 1, 2 & 3a are on disk and green (80 offline passed, 11 deselected). The first task re-verifies interfaces.
- Shared venv Python 3.10 at `../../.venv`; no new deps.
- No `ruff`/`black` → Level 1 is `py_compile` only (incl. the two fixture Python files).
- `make test-gen` + `test_testgen_live.py` make LIVE `claude -p` calls (haiku) — ONE call per generate (cheaper
  than the multipass demos). Not run by `make test`.
- Prompt calibration is empirical: if haiku doesn't reliably propose the out-of-range case, iterate
  `generate-tests.md` wording (fixture/prompt is ground truth) or run on sonnet as a documented fallback — never
  loosen the assert.
- The fixture `tests/test_discount.py` must NOT be collected by the project pytest run (`testpaths = tests` at the
  repo root confines collection) — verify the offline count only grows by the two new `tests/test_testgen*.py`.

**Out of scope for Phase 3b (do not build):** `detected_pattern` dismissal tracking + category quarantine
(TR9/FR4 — Phase 4); real `gh --post` posting (Phase 4); a generic `make test-gen PR=<path>` CLI over an arbitrary
project's tests (noted follow-up); re-run persistence/dedupe of test suggestions (the existing tests are the prior).

**Confidence for one-pass execution:** **8/10.** The spine is solid and thoroughly reused; the pure modules
(`testgen_schema`, `parse_testgen`, `existing_test_names`, `dedupe_suggestions`, `skip_covered`, `score_testgen`)
and the offline orchestration test are fully deterministic; the fixture's covered-vs-uncovered split is
unambiguous; and the review path is untouched except one non-regressive glob generalization (regression-tested).
The one live-behavior risk is haiku reliably proposing the uncovered ValueError case and skipping the single
covered happy path — robust given the clean fixture, with the documented sonnet/prompt-iteration fallback. The
minor open question is the `ast.parse` check on generated code (kept if haiku emits clean pytest, relaxed to
non-empty otherwise) — a calibration detail, not a design risk.
```
