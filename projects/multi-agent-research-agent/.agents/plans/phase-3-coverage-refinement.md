# Feature: Phase 3 — Coverage + Refinement (TR4, TR5)

This plan is complete, but **validate documentation and codebase patterns before implementing.**
Phase 3 has **no new SDK mechanic** to spike (unlike Phase 1's delegation-tool and Phase 2's
parallel-runtime spikes) — the whole capability is Python orchestration + prompt engineering + one
pure evaluator. The single live-dependent risk is a **prompt contract** (does the coordinator emit a
parseable `COVERAGE:` block, and does the partial fixture reliably under-cover?), so Task 1 is a
cheap prompt-contract spike, not an SDK spike.

Pay special attention to existing names/patterns: `AgentRun`, `run_turn`, `run_research`,
`build_*_options`, `triage.classify`, `corpus.FACETS`, `config.MAX_REFINEMENT_ITERATIONS`. This
project uses **flat absolute imports** off `src/` (`import config`, `from loop import run_turn`),
wired by `tests/conftest.py`. Do NOT introduce package-relative imports. The codebase is uniformly
Python **snake_case** — the global camelCase preference yields to the project convention.

## Feature Description

Phase 2 delivered parallel fan-out + deterministic triage. The coordinator fans out to `web_search`
+ `doc_analysis` and synthesizes a cited briefing, but it **never verifies that the report actually
spanned the whole topic**, and it has **no way to recover from an under-covered first pass**. Phase 3
adds the two capabilities that guarantee breadth:

1. **Scope partitioning + coverage verification (TR4/FR2):** the coordinator assigns each facet to a
   distinct subagent (minimizing duplicate retrieval) and emits a machine-readable `COVERAGE:` block.
   A **pure evaluator** compares the covered facets against the ground-truth facet set
   (`corpus.FACETS`) — killing the canonical "only visual arts" failure.
2. **Iterative refinement (TR5):** when the evaluator finds a gap, a **code-orchestrated bounded
   loop** re-delegates a targeted query for the missing facets (passing the prior draft as explicit
   context) and re-synthesizes the complete briefing, up to `MAX_REFINEMENT_ITERATIONS` (=2).

This is where the long-stubbed **coverage/gaps concepts come alive** — the data is now produced and
verified. (Assembling a full `schemas.Report` with per-claim provenance stays Phase 4, which owns
claim→source parsing.)

Everything is validated on **structure** (parsed coverage maps, gap lists, iteration counts),
never on the model's prose — the house ethos.

## User Story

As a **research requester**
I want the briefing to cover the **whole** topic, and to self-heal when a first pass misses a facet,
So that **I am never misled by a report that silently covered only one facet.**

Supporting PRD stories (§5): #2 (report covers the whole topic; no silent omissions), and the
refinement quality indicator in §11 ("refinement closes an injected coverage gap").

## Problem Statement

- Phase 2's coordinator produces a report but **does not verify coverage**. If it under-covers (the
  "only visual arts" trap, TR4/FR2), nothing detects it — the PRD acceptance criterion "a broad topic
  produces coverage across all major facets" is unproven.
- There is **no refinement loop**. TR5 ("evaluate for coverage gaps, re-delegate, re-synthesize
  until sufficient") is unmet; `config.MAX_REFINEMENT_ITERATIONS` is defined but unused.
- `Report.coverage` / `Report.gaps` have been **stubbed since Phase 1** with no producer.

## Solution Statement

- **Pure coverage evaluator (`src/coverage_eval.py`):** parses the coordinator's `COVERAGE:` block
  into `{facet: status}`, maps free-text facet labels to canonical facets via a lenient alias table,
  and compares against an **expected facet set** (default `corpus.FACETS`) to compute `gaps`. SDK-free,
  100% unit-testable without credentials (mirrors `triage.py`). A prose-scan fallback protects against
  a missing/malformed block causing needless refinement.
- **Code-orchestrated bounded refinement loop:** `run_research()`'s fan-out path calls a new
  `_run_with_refinement(question, initial_options, expected_facets)` helper: run turn 1 → evaluate
  coverage → while gaps remain and under the cap, run a **refinement turn** (full coordinator, prompt
  names the missing facets + carries the prior draft) → re-evaluate. The counter lives in code, so the
  bound and the gap-trigger are deterministic and testable.
- **Scope partitioning via prompt + verification:** the `SYSTEM_PROMPT` gains an explicit
  "one facet per `web_search` delegation, don't overlap" instruction and the `COVERAGE:` block
  contract; coverage is *verified* by the evaluator against ground truth.
- **Partial-coordinator fixture (`build_partial_coordinator_options()`):** a permanent, deliberately
  under-covering config (twin of `build_no_delegation_options()`) that covers only 2 facets on the
  first pass — the live test's injected gap, so gap-closing is proven end-to-end, not just in a unit.
- **Instrumentation:** `AgentRun` gains `coverage`, `gaps`, `refinement_iterations`, and
  `coverage_history` — all set by `run_research()` (the loop stays coverage-agnostic, exactly as
  `route` already is).

## Feature Metadata

**Feature Type:** Enhancement (extends the Phase-2 parallel coordinator).
**Estimated Complexity:** **Medium** — no SDK unknown; the evaluator + bounded loop are pure/plumbing,
and the loop logic is fully unit-testable via a monkeypatched `run_turn`. Residual risk is prompt
reliability (COVERAGE-block emission), quarantined into the Task-1 spike.
**Primary Systems Affected:** new `src/coverage_eval.py`; `src/coordinator.py` (prompt + partial
builder + refinement loop); `src/loop.py` (`AgentRun` fields); `run_example.py`; `tests/`.
**Dependencies:** No new packages. Uses `corpus.FACETS`, `config.MAX_REFINEMENT_ITERATIONS`
(both already defined).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `src/coordinator.py` (whole file) — **Why:** you (a) extend `SYSTEM_PROMPT` with the partitioning
  line + `COVERAGE:` block contract, (b) add `build_partial_coordinator_options()`, (c) add the
  refinement-prompt builder + `_run_with_refinement()`, (d) rewrite `run_research()` to route then
  refine. Keep the verified delegation recipe (`tools=["Agent"]`, MCP tool in `allowed_tools`,
  external stdio server, `strict_mcp_config`) unchanged. `_SEQUENTIAL_SYSTEM_PROMPT` and
  `build_single_agent_options()` are unchanged (see GOTCHA in Task 4).
- `src/loop.py` — **Why:** add coverage/refinement fields to `AgentRun` (set by `run_research`, like
  `route`). **Do NOT** add message parsing — no new SDK message types are involved. Preserve every
  Phase-1/2 invariant (coordinator-level `parent_tool_use_id is None` filter, keep LAST
  `ResultMessage`, drain the stream / never `break`).
- `src/triage.py` — **Why:** the template for a pure, SDK-free, deterministic module with string-
  constant statuses and module-level word/marker tables. `coverage_eval.py` mirrors its shape.
- `src/mocks/corpus.py` — **Why:** `FACETS = ["visual_art","music","writing","film"]` (line 24) is
  the ground-truth expected set the evaluator checks against. `search(query, facet=...)` already
  scopes retrieval by facet (line 146) — the partitioning seam. SDK-free.
- `src/config.py` — **Why:** `MAX_REFINEMENT_ITERATIONS = 2` (line 42) is now USED (update its
  comment from "UNUSED until Phase 3" to "used by the refinement loop"). No other change.
- `src/schemas.py` — **Why:** reference only. `Report.coverage: dict[str,str]` + `Report.gaps:
  list[str]` (lines 61–62) are the shapes `run.coverage`/`run.gaps` mirror. Do NOT assemble a full
  `Report` here (claims parsing is Phase 4) — see NOTES.
- `tests/conftest.py` — **Why:** `run_research` fixture (lazy SDK import), `agent_runnable()` gate.
  You add a fixture that drives `_run_with_refinement` with the partial coordinator.
- `tests/test_coordinator_config.py` — **Why:** the unit pattern for builder-shape assertions (no
  API). Extend for `build_partial_coordinator_options()` + the `COVERAGE:` instruction.
- `tests/test_phase2_parallel_live.py` — **Why:** the integration-test shape to mirror (marker gate,
  structural assertions, `_FACET_KEYWORDS` lenient breadth signal, citation guard).
- `run_example.py` — **Why:** extend the printout with coverage/gaps/refinement lines.
- `_tasks/todo.md` — **Why:** the Phase-2 handoff note (lines 204–206) IS this plan's charter:
  "scope partitioning + the refinement loop; Report.coverage/gaps come alive here."

### New Files to Create

- `src/coverage_eval.py` — pure coverage evaluator. **Named `coverage_eval`, NOT `coverage`, to avoid
  shadowing the ubiquitous `coverage.py` library** under the flat `src/`-on-path import scheme
  (footgun if `pytest-cov` is ever added). SDK-free.
- `tests/test_coverage.py` — deterministic unit table for the evaluator.
- `tests/test_refinement_loop.py` — deterministic loop-logic test via a **monkeypatched `run_turn`**
  (no API): proves the loop stops on full coverage, iterates on gaps, is bounded by
  `MAX_REFINEMENT_ITERATIONS`, and records `coverage_history` correctly.
- `tests/test_phase3_coverage_live.py` — integration (`-m integration`): happy-path full coverage +
  injected-gap refinement via the partial coordinator.

### Relevant Documentation

- Spec (source of truth) `docs/02-multi-agent-research-system.md` — TR4 (lines 48–49), TR5 (50–51),
  acceptance (line 91), Phase-3 validate (81–82).
- PRD `docs/02-multi-agent-research-prd.md` — §12 Phase 3 (222–225), §6 refinement-loop pattern
  (line 138), §14 narrow-decomposition risk row (line 244).
- Memory `mar-agent-sdk-delegation` — the delegation/parallel recipe (unchanged; refinement re-uses
  the same `build_coordinator_options()` for re-delegation).

### Patterns to Follow

**Status constants (mirror `triage.py:33-34`):**
```python
# src/coverage_eval.py
STATUS_COVERED = "covered"
STATUS_PARTIAL = "partial"
STATUS_GAP = "gap"
```

**Pure-module style (mirror `triage.py` / `mocks/corpus.py`):** module-level alias table + small pure
functions; total & deterministic; never raises; no SDK, no API.

**`AgentRun` extension (mirror the `route` precedent, `loop.py:103`):** new fields default-empty and
are set by `run_research()` after the turn(s); the loop never touches them.

**Test split (mirror `conftest.py` + `test_phase2_parallel_live.py`):** deterministic units import
nothing SDK-backed at collection time (or only cheap dataclass construction, no network); live tests
carry `pytestmark = [pytest.mark.integration, pytest.mark.skipif(not agent_runnable(), ...)]`.

---

## IMPLEMENTATION PLAN

### Phase A (De-risk): prompt-contract spike (Task 1)
Confirm the `COVERAGE:` block is emitted parseably by the full coordinator (all 4 facets covered) and
that the partial fixture under-covers to exactly 2. Cheap, run once.

### Phase B (Pure core): evaluator + instrumentation (Tasks 2–3)
Build `coverage_eval.py` and the `AgentRun` fields — both unit-testable immediately, no API.

### Phase C (Orchestration): prompt, partial fixture, refinement loop, routing (Tasks 4–8)
Extend the system prompt; add the partial builder; add the refinement prompt + `_run_with_refinement`;
wire `run_research`; extend `run_example.py`.

### Phase D (Validation): units + live + regression (Tasks 9–13)
Evaluator table; monkeypatched loop test; config-test extension; live coverage + injected-gap tests;
regression + memory + todo review.

---

## STEP-BY-STEP TASKS

Execute in order. Tasks 2–3 (pure core) are testable before any API call; Task 1 (spike) gates the
prompt wording in Tasks 4–5.

### Task 1 — Prompt-contract spike (scratchpad, run ONCE)  ⚠️ linchpin

- **IMPLEMENT:** a throwaway script under the session scratchpad (NOT the repo) that:
  1. Runs the full parallel coordinator (draft `SYSTEM_PROMPT` + COVERAGE-block instruction) on the
     canonical broad question; prints `run.final_text` and whether a `COVERAGE:` block is present and
     parseable into all 4 canonical facets marked `covered`.
  2. Runs a draft partial coordinator (system prompt: "cover ONLY visual art and music; do not
     research writing or film") on the same question; confirms its block lists only 2 facets (a real
     injected gap).
- **DECISION:** if the full coordinator reliably emits a parseable block covering all 4, and the
  partial reliably under-covers → lock the prompt wording into Tasks 4–5. If the block format drifts,
  tighten the format instruction (exact `- <facet>: <status>` lines) and re-run once.
- **GOTCHA:** keep subagent-facing text benign/research-framed (org guardrail — memory note). Costs a
  few live runs — run once, capture output, delete the script.
- **VALIDATE:** `../../.venv/bin/python <scratchpad>/spike_coverage.py` → read output; confirm both
  contract behaviors before proceeding.

### Task 2 — CREATE `src/coverage_eval.py`: pure coverage evaluator (TR4)

- **IMPLEMENT:**
  - Module docstring tying to TR4/TR5; note SDK-free + deterministic.
  - `STATUS_COVERED/PARTIAL/GAP` constants.
  - `FACET_ALIASES: dict[str, tuple[str, ...]]` — canonical facet → substrings that map to it, e.g.
    `{"visual_art": ("visual", "art", "illustrat", "image"), "music": ("music", "song", "audio"),
    "writing": ("writ", "author", "publish", "text"), "film": ("film", "movie", "cinema", "video")}`.
    Keyed by `corpus.FACETS` values.
  - `canonical_facet(label: str) -> str | None` — lowercase `label`, return the first canonical facet
    whose any alias is a substring; else `None`.
  - `parse_coverage_block(report_text: str) -> dict[str, str]` — find a line starting `COVERAGE:`
    (case-insensitive), parse subsequent `- <label>: <status>` lines until a blank line / non-matching
    line; map each label via `canonical_facet`, keep the last status per canonical facet, normalize
    status to one of the three constants (unknown → `STATUS_PARTIAL`). Returns `{}` if no block.
  - `facet_mentioned(facet: str, text: str) -> bool` — any alias substring appears in `text.lower()`
    (the prose-scan fallback).
  - `evaluate(report_text: str, expected_facets: list[str]) -> CoverageResult` (a small
    `@dataclass`: `map: dict[str,str]`, `covered: set[str]`, `gaps: list[str]`):
    - `declared = parse_coverage_block(report_text)`.
    - `covered = {f for f in expected if declared.get(f) == STATUS_COVERED}`.
    - **Fallback:** if `not declared`, `covered = {f for f in expected if facet_mentioned(f,
      report_text)}` (a well-covered report without a clean block isn't falsely flagged).
    - `gaps = [f for f in expected if f not in covered]` (order follows `expected`).
    - `map` = `declared` if present else `{f: (COVERED if f in covered else GAP) for f in expected}`.
- **PATTERN:** `src/triage.py` (pure module, constants + small functions, module-level tables).
- **IMPORTS:** stdlib only (`re` optional; `dataclasses`). Do NOT import the SDK. May import
  `corpus`/`config` only if reading defaults — prefer taking `expected_facets` as a param (caller
  passes `corpus.FACETS`) to keep this module dependency-light and trivially testable.
- **GOTCHA:** total & deterministic (never raise; same input → same output). Canonical mapping order
  matters — put `film`'s `"video"` alias carefully (avoid mapping "music video" wrongly; test both).
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import coverage_eval
  as c; print(c.evaluate('COVERAGE:\n- visual art: covered\n- music: covered', ['visual_art','music',
  'writing','film']).gaps)"` → prints `['writing', 'film']`.

### Task 3 — UPDATE `src/loop.py`: add coverage/refinement fields to `AgentRun`

- **IMPLEMENT:** add fields (defaults empty; **set by `run_research`, never by the loop** — mirror the
  `route` comment):
  - `refinement_iterations: int = 0`
  - `coverage: dict = field(default_factory=dict)`  # final canonical facet → status
  - `gaps: list = field(default_factory=list)`       # final unresolved canonical facets
  - `coverage_history: list = field(default_factory=list)`  # coverage map after each turn (proves progression)
  - Optionally a `@property fully_covered` → `not self.gaps`.
- **PATTERN:** `src/loop.py:103` (`route: Optional[str] = None  # set by run_research()`), and the
  existing `@property` block (114–174).
- **IMPORTS:** none new.
- **GOTCHA:** do NOT add any `Task*Message`/parsing logic — Phase 3 introduces no new stream messages.
  The loop stays route- and coverage-agnostic; `run_turn` is unchanged.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import loop;
  r=loop.AgentRun(); print(r.refinement_iterations, r.coverage, r.gaps, r.fully_covered)"` →
  prints `0 {} [] True`.

### Task 4 — UPDATE `src/coordinator.py`: partitioning + `COVERAGE:` block in `SYSTEM_PROMPT`

- **IMPLEMENT:** extend the parallel `SYSTEM_PROMPT` (only) with:
  - A partitioning line: "Assign each facet to a SEPARATE `web_search` delegation — one facet per
    subagent — so no two subagents retrieve the same facet (minimize duplicate work)."
  - The coverage contract (append near the end, after the synthesis instructions): "End your briefing
    with a machine-readable coverage block, on its own lines, in EXACTLY this format:
    ```
    COVERAGE:
    - <facet name>: <covered|partial|gap>
    ```
    one line per facet you addressed, marking `covered` only if you found real sourced evidence for it,
    `partial` if thin, `gap` if you could not cover it." Use the wording locked by the Task-1 spike.
- **PATTERN:** `src/coordinator.py:68-109` (existing `SYSTEM_PROMPT`).
- **IMPORTS:** none.
- **GOTCHA:** do NOT add the coverage block to `_SEQUENTIAL_SYSTEM_PROMPT` — it is retained VERBATIM
  as the benchmark baseline only (`benchmark_parallel.py`), and coverage isn't measured there. Do NOT
  hand the coordinator the canonical facet vocabulary (`visual_art`, …) — it decomposes freely; the
  evaluator's alias table bridges its labels to canonical facets (keeps decomposition honest, TR4).
  The existing Phase-1/2 non-negotiables (both subagents, `[source, date]` on every claim, no
  "launched agents" finish) MUST remain.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from coordinator
  import SYSTEM_PROMPT; print('COVERAGE:' in SYSTEM_PROMPT, 'one facet' in SYSTEM_PROMPT.lower())"` →
  prints `True True`.

### Task 5 — ADD `build_partial_coordinator_options()` to `src/coordinator.py` (live gap fixture)

- **IMPLEMENT:** a permanent fixture identical to `build_coordinator_options()` (delegation-capable:
  `tools=["Agent"]`, both subagents, external stdio MCP, `strict_mcp_config`, `max_turns`) EXCEPT its
  `system_prompt` is a deliberately under-covering variant (`_PARTIAL_SYSTEM_PROMPT`): "Research ONLY
  the visual art and music facets. Do NOT research writing or film. End with the COVERAGE block for
  the facets you covered." Docstring: "Permanent negative/acceptance fixture (twin of
  `build_no_delegation_options`): deliberately under-covers so the refinement loop's gap-closing can
  be proven live."
- **PATTERN:** `src/coordinator.py:171-208` (`build_coordinator_options` / `build_sequential_*`).
- **IMPORTS:** none.
- **GOTCHA:** it MUST stay delegation-capable (so it actually produces a real 2-facet report to
  refine), and MUST still emit a COVERAGE block (so the evaluator sees only 2 covered). Keep text
  benign.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from coordinator
  import build_partial_coordinator_options as f, build_coordinator_options as g; a=f();
  print(a.tools==['Agent'], set(a.agents)=={'web_search','doc_analysis'}, a.system_prompt!=g().system_prompt)"`
  → prints `True True True`.

### Task 6 — ADD refinement prompt builder + `_run_with_refinement()` to `src/coordinator.py` (TR5)

- **IMPLEMENT:**
  - `_build_refinement_prompt(question: str, prior_draft: str, missing: list[str]) -> str` — a turn
    prompt (NOT a system prompt) that carries explicit context (TR2): the original question, the prior
    draft verbatim, the explicit missing-facet list, and the instruction: "This briefing is INCOMPLETE
    — it is missing these facets: {missing}. Delegate to `web_search` for ONLY those missing facets,
    then produce the COMPLETE updated briefing covering ALL facets (keep the existing well-covered
    sections, add the missing ones), ending with the COVERAGE block. Every claim keeps `[source,
    date]`."
  - `async def _run_with_refinement(question, initial_options, expected_facets) -> AgentRun`:
    ```
    run = await run_turn(question, initial_options)
    result = coverage_eval.evaluate(run.final_text, expected_facets)
    history = [result.map]
    iterations = 0
    while result.gaps and iterations < config.MAX_REFINEMENT_ITERATIONS:
        iterations += 1
        prompt = _build_refinement_prompt(question, run.final_text, result.gaps)
        run = await run_turn(prompt, build_coordinator_options())   # full coordinator fills the gaps
        result = coverage_eval.evaluate(run.final_text, expected_facets)
        history.append(result.map)
    run.refinement_iterations = iterations
    run.coverage = result.map
    run.gaps = result.gaps
    run.coverage_history = history
    return run
    ```
    (Refinement turns ALWAYS use the full `build_coordinator_options()`, so an under-covering *initial*
    config — the partial fixture in tests — is corrected by the full coordinator guided by the missing
    list. In production `initial_options` IS the full coordinator, so this is a no-op difference.)
- **PATTERN:** `src/coordinator.py:258-273` (current `run_research`); the loop follows the "counter in
  code, bounded by config" ethos of `triage`/instrumentation.
- **IMPORTS:** `import coverage_eval` (flat, `src/` on path); `from mocks import corpus` is NOT needed
  here (expected_facets is a param).
- **GOTCHA:** each `run_turn` returns a FRESH `AgentRun`; the loop overwrites `run`, so the returned
  run's `tool_calls`/`delegations`/`peak_concurrent_tasks` reflect the LAST turn (fine — the final
  synthesis). Cross-turn coverage progression is preserved via `coverage_history`. Bound is the cap
  even if gaps persist (don't loop forever). `final_text` may be ~2k tokens — acceptable in a prompt.
- **VALIDATE:** exercised by Task 10 (monkeypatched, no API) + Task 12 (live).

### Task 7 — UPDATE `run_research()` in `src/coordinator.py`: route then refine

- **IMPLEMENT:**
  ```python
  from mocks import corpus
  async def run_research(question: str) -> AgentRun:
      route = triage.classify(question)
      if route == triage.ROUTE_SINGLE_AGENT:
          run = await run_turn(question, build_single_agent_options())
          run.route = route
          return run                     # narrow lookup: no facet coverage / refinement
      run = await _run_with_refinement(question, build_coordinator_options(), corpus.FACETS)
      run.route = route
      return run
  ```
- **PATTERN:** `src/coordinator.py:258-273` (existing routing).
- **IMPORTS:** `from mocks import corpus` at module top (already importable — the external server
  imports it too).
- **GOTCHA:** the single-agent path is UNCHANGED (leaves `coverage={}`, `gaps=[]`,
  `refinement_iterations=0`). Keep `run.route` stamped last. Phase-2 live tests
  (`test_phase2_parallel_live.py`) assert on the broad path's `peak_concurrent_tasks`/`subtype`/
  citations — the FIRST turn still fans out identically, and when coverage is full (expected happy
  path) `refinement_iterations==0` so those tests still see a single-turn run. Verify no regression.
- **VALIDATE:** Task 12 live + regression run.

### Task 8 — UPDATE `run_example.py`: print coverage/gaps/refinement (TR4/TR5 visibility)

- **IMPLEMENT:** add lines after the existing outcome prints:
  `COVERAGE:` (`run.coverage`), `GAPS:` (`run.gaps`), `REFINEMENT ITERATIONS:`
  (`run.refinement_iterations`), and optionally `COVERAGE HISTORY:` (`run.coverage_history`).
- **PATTERN:** `run_example.py:18-30`.
- **VALIDATE:** `../../.venv/bin/python run_example.py` → prints a report with a coverage map spanning
  all 4 facets and `REFINEMENT ITERATIONS: 0` on a clean run.

### Task 9 — CREATE `tests/test_coverage.py`: evaluator unit table (deterministic, no API)

- **IMPLEMENT:** parametrized/explicit cases on `coverage_eval`:
  - `parse_coverage_block`: a clean block → all 4 canonical facets with statuses; free-text labels
    ("visual arts", "written word", "movies") map via aliases; no block → `{}`.
  - `evaluate` (expected = `corpus.FACETS`):
    - full-coverage block → `gaps == []`, `map` all covered.
    - 2-facet block ("visual art", "music" covered) → `gaps == ["writing", "film"]` (order = expected).
    - a facet marked `gap`/`partial` in the block → appears in `gaps`.
    - **fallback:** no block but report prose mentions all 4 facet names → `gaps == []` (no false
      refinement); prose mentions only 2 → the other 2 in `gaps`.
    - alias edge: "music video" does NOT get miscounted as `film` coverage (guard the alias table).
  - `canonical_facet`: representative labels → expected canonical; unrelated label → `None`.
- **PATTERN:** `tests/test_triage.py` boundary-table style (pure function, no SDK/API).
- **IMPORTS:** `import coverage_eval`; `from mocks import corpus`; `import pytest`.
- **VALIDATE:** `../../.venv/bin/pytest tests/test_coverage.py -q` → all pass, <1s.

### Task 10 — CREATE `tests/test_refinement_loop.py`: bounded loop logic (deterministic, no API)

- **IMPLEMENT:** unit-test `_run_with_refinement` with a **monkeypatched `run_turn`** so NO API is
  called. Use `monkeypatch.setattr(coordinator, "run_turn", fake)` where `fake` is an async callable
  returning a canned `AgentRun` with a chosen `final_text` (COVERAGE block) per call:
  - **Full coverage on turn 1:** fake returns an all-4-covered block → assert
    `refinement_iterations == 0`, `gaps == []`, `len(coverage_history) == 1`.
  - **Gap then closed:** fake returns a 2-facet block first, an all-4 block second → assert
    `refinement_iterations == 1`, final `gaps == []`, `len(coverage_history) == 2`, and
    `coverage_history[0]` had gaps.
  - **Persistent gap → bounded:** fake always returns a 2-facet block → assert
    `refinement_iterations == config.MAX_REFINEMENT_ITERATIONS`, final `gaps` non-empty (loop stopped
    at the cap, did not run forever), `len(coverage_history) == MAX_REFINEMENT_ITERATIONS + 1`.
  - Assert `fake` call-count matches `1 + refinement_iterations` (each iteration ran exactly one turn).
- **PATTERN:** monkeypatch pattern; construct `AgentRun` directly (it's a plain dataclass — cheap, no
  SDK run). This is the deterministic proof of TR5's bounded loop.
- **IMPORTS:** `import coordinator`, `import config`, `from loop import AgentRun`, `import pytest`.
  Note: importing `coordinator` pulls SDK types (no API call) — acceptable in the default suite
  (precedent: `test_coordinator_config.py`).
- **GOTCHA:** `_run_with_refinement` calls `build_coordinator_options()` on refinement turns — that
  constructs options (no API) and is fine; only `run_turn` (the API driver) is faked. Make `fake`
  accept `(prompt, options)` to match the signature.
- **VALIDATE:** `../../.venv/bin/pytest tests/test_refinement_loop.py -q` → all pass, no network.

### Task 11 — UPDATE `tests/test_coordinator_config.py`: partial builder + coverage contract

- **IMPLEMENT:** add cases:
  - `build_partial_coordinator_options()`: `tools == ["Agent"]`, both subagents registered,
    `_WEB_SEARCH_TOOL in allowed_tools`, and `system_prompt != build_coordinator_options().system_prompt`.
  - `SYSTEM_PROMPT` contains the coverage contract: `"COVERAGE:" in SYSTEM_PROMPT` and a partitioning
    phrase (lenient substring).
- **PATTERN:** `tests/test_coordinator_config.py:58-77`.
- **IMPORTS:** add `build_partial_coordinator_options`, `SYSTEM_PROMPT` to the existing import.
- **VALIDATE:** `../../.venv/bin/pytest tests/test_coordinator_config.py -q` → all pass.

### Task 12 — CREATE `tests/test_phase3_coverage_live.py`: coverage + injected-gap refinement (live)

- **IMPLEMENT:** mirror `test_phase2_parallel_live.py` header (imports, `pytestmark` marker+skipif).
  - `test_broad_query_covers_all_facets`: `run = await run_research(BROAD_Q)`. Assert
    `run.route == triage.ROUTE_FAN_OUT`; `coverage_eval.evaluate(run.final_text, corpus.FACETS).gaps
    == []` OR `run.gaps == []`; `run.coverage` marks all 4 canonical facets; `run.subtype ==
    "success"`; final text spans ≥3 facet keywords + a citation bracket + a corpus year (happy path;
    `refinement_iterations` likely 0 but not asserted to a fixed value).
  - `test_injected_gap_triggers_refinement`: drive `_run_with_refinement(BROAD_Q,
    build_partial_coordinator_options(), corpus.FACETS)` (via a conftest fixture). Assert
    `run.refinement_iterations >= 1`; `run.coverage_history[0]` had gaps including `writing`/`film`;
    final `run.gaps == []` (or strictly fewer than the first pass); final `run.coverage` now marks all
    4 covered; final text now mentions the previously-missing facets. **This is the TR5 acceptance
    demo — a real gap closed end-to-end.**
- **PATTERN:** `tests/test_phase2_parallel_live.py` (marker gate, structural assertions, citation +
  facet-keyword guards). Add a `run_with_refinement` / `run_partial_then_refine` fixture to
  `conftest.py` (lazy import of `_run_with_refinement` + `build_partial_coordinator_options`).
- **IMPORTS:** `import config, triage, coverage_eval`; `from mocks import corpus`; `import pytest`.
- **GOTCHA:** live/costly (the injected-gap test runs ≥2 full coordinator turns) — gated behind
  `-m integration`, skipped without CLI/API. If the coordinator occasionally covers all 4 despite the
  partial prompt (prompt not perfectly obeyed), the injected-gap test would see `iterations==0` and
  fail — the Task-1 spike de-risks this; if flaky, strengthen `_PARTIAL_SYSTEM_PROMPT`.
- **VALIDATE:** `../../.venv/bin/pytest -m integration tests/test_phase3_coverage_live.py -q`
  (requires credentials) → passes.

### Task 13 — Regression, memory, and `_tasks/todo.md` review

- **IMPLEMENT:** run the full default suite + live suite; append the Phase-3 checklist + review to
  `_tasks/todo.md` (mirror the Phase-1/2 structure: scope guardrails, steps, validation checkboxes,
  review). Update memory `mar-agent-sdk-delegation` (or a new note) ONLY if the spike surfaced a
  non-obvious prompt/SDK fact worth persisting.
- **VALIDATE:** `../../.venv/bin/pytest -q` (units green, fast) then `../../.venv/bin/pytest -m
  integration -q` (live green, incl. Phase-1/2 regression).

---

## TESTING STRATEGY

### Unit Tests (default `pytest`, deterministic, free)
- `test_coverage.py` — evaluator: block parse, alias mapping, gap computation, prose-scan fallback,
  alias edge cases. Pure, no SDK.
- `test_refinement_loop.py` — bounded loop via monkeypatched `run_turn`: stops on full coverage,
  iterates on gaps, bounded by `MAX_REFINEMENT_ITERATIONS`, `coverage_history` correct. No network.
- `test_coordinator_config.py` (extended) — partial builder shape + `COVERAGE:`/partitioning contract
  in `SYSTEM_PROMPT`.

### Integration Tests (`pytest -m integration`, live)
- `test_phase3_coverage_live.py` — full-coverage happy path + injected-gap refinement (partial
  coordinator → refinement closes writing/film).
- Regression: `test_phase1_spine_live.py` + `test_phase2_parallel_live.py` still pass under the
  refinement-wrapped `run_research` (broad path unchanged when coverage is full on turn 1).

### Edge Cases
- **Malformed / missing COVERAGE block** → evaluator prose-scan fallback prevents false refinement
  (unit-covered).
- **Persistent gap** (a facet genuinely uncoverable) → loop stops at the cap, `gaps` non-empty, report
  still ships (annotation of that residual gap is Phase 4/TR9).
- **Alias collision** ("music video") → guarded by the alias-table test.
- **Single-agent route** → no coverage/refinement applied (asserted indirectly: narrow lookup leaves
  `coverage=={}`).

---

## VALIDATION COMMANDS

Run from project root `projects/multi-agent-research-agent/`. Python: `../../.venv/bin/python`.

### Level 1: Syntax & Import Sanity
```
../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import coverage_eval, loop, config, coordinator, triage; print('imports ok')"
```
### Level 2: Unit Tests (deterministic, free)
```
../../.venv/bin/python -m pytest -q                       # full default suite (57 prior + new units), ~1-2s
../../.venv/bin/python -m pytest tests/test_coverage.py tests/test_refinement_loop.py tests/test_coordinator_config.py -q
```
### Level 3: Integration Tests (live)
```
../../.venv/bin/python -m pytest -m integration -q        # incl. Phase-1/2 regression + Phase-3
```
### Level 4: Manual Validation
```
../../.venv/bin/python run_example.py                     # broad Q → coverage spans all 4 facets, REFINEMENT ITERATIONS: 0
```

---

## ACCEPTANCE CRITERIA

- [ ] **Full-topic coverage verified:** a broad question yields `run.gaps == []` with `run.coverage`
      marking all 4 canonical facets covered (TR4); the "only-one-facet" failure is detectable and gone.
- [ ] **Refinement closes an injected gap:** the partial coordinator under-covers to 2 facets, and
      `_run_with_refinement` drives `refinement_iterations >= 1` to a final all-4-covered report with
      `gaps == []` (TR5) — proven live, end-to-end.
- [ ] **Loop is deterministically bounded:** `test_refinement_loop.py` proves stop-on-coverage,
      iterate-on-gap, and the `MAX_REFINEMENT_ITERATIONS` cap — no API, no infinite loop.
- [ ] **Evaluator is pure & correct:** `test_coverage.py` green — block parse, alias mapping, gap
      computation, prose-scan fallback all verified without credentials.
- [ ] **No regressions:** default suite fast+green; Phase-1/2 live tests still pass under the
      refinement-wrapped `run_research`; `test_coordinator_config.py` green.
- [ ] **Visibility:** `run_example.py` prints the coverage map, gaps, and refinement iterations.
- [ ] Conventions honored (snake_case, flat imports, TR-tagged docstrings, structure-only assertions).

---

## COMPLETION CHECKLIST

- [ ] Task 1 spike run ONCE; COVERAGE-block contract + partial under-coverage confirmed; wording locked.
- [ ] Tasks 2–3 (evaluator, `AgentRun` fields) done, unit-covered by Tasks 9–10.
- [ ] Tasks 4–7 (prompt contract, partial builder, refinement loop, routing) done, each validated.
- [ ] Task 8 (`run_example.py`) prints coverage/gaps/refinement.
- [ ] Tasks 9–12 (all tests) green: units in default suite, live under `-m integration`.
- [ ] Full suite passes (unit + integration incl. regression); `_tasks/todo.md` Phase-3 review appended.
- [ ] `git diff` reviewed for scope; memory updated only if the spike surfaced something non-obvious.

---

## NOTES

**Confirmed design decisions (this planning conversation):**
- **Refinement loop = code-orchestrated + bounded** (not in-model, not SDK sessions). Rationale: the
  iteration count and gap-trigger become deterministic and unit-testable (monkeypatched `run_turn`),
  matching how triage/instrumentation were resolved. The counter lives in code, bounded by
  `MAX_REFINEMENT_ITERATIONS`.
- **Coverage signal = structured `COVERAGE:` block** emitted by the coordinator, parsed by a pure
  evaluator, with a prose-scan fallback. Robust, fills the long-stubbed coverage concept, and sets up
  Phase 4's TR9 annotations.
- **Gap proof = a permanent partial-coordinator fixture** (twin of `build_no_delegation_options`) that
  deliberately under-covers, so refinement's gap-closing is proven live, not just in a unit test.
- **`run_research` keeps returning `AgentRun`** (tests depend on it); coverage/gaps/refinement are
  ATTACHED to the run (like `route`), rather than switching to the PRD's illustrative `-> Report`
  signature.

**Deliberate Phase-3 scope boundaries (NOT in this phase):**
- **Full `schemas.Report` assembly** (sections + per-claim `Claim`/`SourceRef` parsing) stays
  **Phase 4** — it needs claim→source extraction, which is Phase 4's provenance work. Phase 3 realizes
  the coverage/gaps DATA (on `AgentRun`); Phase 4 assembles the typed `Report` around it and renders
  TR9 coverage annotations by content type.
- **Structured error envelopes, timeout/retry, conflict/temporal annotation** → **Phase 4**
  (TR7/TR8/TR9). The corpus timeout marker (D004) stays inert. A *residual* gap after the cap is left
  as data now; its rendered annotation is Phase 4.
- **Subagent-internal facet-arg capture** (peeking into subagent `web_search(facet=...)` calls to
  prove partitioning at the tool level) was considered and DEFERRED — it adds loop complexity and a
  mild TR6 tension. Partitioning is steered by prompt and *verified* at the report level (coverage
  spans all facets); duplicate-retrieval minimization is a prompt instruction, not an asserted metric.

**Why no heavy SDK spike this phase:** Phase 1 (delegation tool) and Phase 2 (parallel runtime) each
had a genuine SDK unknown. Phase 3 reuses the proven `build_coordinator_options()` for re-delegation
and introduces no new SDK message types — the only live-dependent risk is prompt reliability, covered
by the cheap Task-1 contract spike.

**Confidence: 8/10 for one-pass success.** The evaluator and bounded loop are pure/plumbing and fully
unit-tested without API. The residual risk is prompt obedience — the full coordinator must emit a
parseable COVERAGE block (else the fallback engages), and the partial fixture must reliably
under-cover so the live gap-closing test isn't a no-op. Both are pinned by the Task-1 spike; a
stubborn model could need one prompt iteration (hence 8, not 9).
