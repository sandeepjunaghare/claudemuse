# Phase 1 — Spine

> Goal: the minimal working hub-and-spoke. Coordinator delegates to `web_search` +
> `doc_analysis` via the SDK `Task` tool; each subagent explores in an isolated window
> and returns a distilled summary; the **coordinator** does a single synthesis pass into
> a basic cited report. Prove: `Task` fires, subagents receive context *only* via prompt,
> a report is produced, and the **no-`Task` failure** is demonstrable.
>
> Source of truth: `docs/02-multi-agent-research-system.md` (TR1–TR10). PRD: `docs/02-multi-agent-research-prd.md` §12.
> Confirmed decisions: synthesis = **coordinator-owned**; corpus = **full/forward-compatible**; testing = **deterministic-first + a few integration-marked live tests**.

## Scope guardrails (what Phase 1 does NOT do)
- ❌ Parallel `Task` fan-out + dynamic selection (Phase 2) — Phase 1 delegation may be sequential.
- ❌ Scope partitioning + refinement loop (Phase 3).
- ❌ Structured error envelopes, provenance/conflict/temporal handling, coverage annotations (Phase 4).
- Corpus is *seeded* with conflict/dated/timeout entries as **data**, but Phase 1 only wires clean retrieval; the behaviors that exercise them arrive in later phases.

---

## Step 0 — De-risk the `tools` / `allowed_tools` / `Task` interaction  ⚠️ linchpin
The sibling uses `tools=[]`, which strips built-in tools **including `Task`** → a coordinator that cannot delegate. Must resolve before anything else.
- [ ] Spike: confirm the coordinator can keep `Task` while denying Bash/Read/Write. Expected answer: **do not** set `tools=[]`; instead use `allowed_tools=["Task", "mcp__<server>__web_search"]` as the allowlist (built-ins registered but not permitted). Verify empirically with a throwaway `query()`.
- [ ] Record the confirmed recipe as a comment in `coordinator.py` and (if non-obvious) a memory note.

## Step 1 — Project scaffold + deps
- [ ] `requirements.txt` — `claude-agent-sdk`, `pytest`, `pytest-asyncio`, `python-dotenv` (mirror sibling).
- [ ] `pip install -r requirements.txt` into shared venv `../../.venv`.
- [ ] `pytest.ini` — `asyncio_mode = auto`, `testpaths = tests`, `integration` marker (mirror sibling).
- [ ] `src/__init__.py`, `src/config.py` — `COORDINATOR_MODEL = "claude-opus-4-8"`, `WORKER_MODEL = "claude-sonnet-4-6"`, `MCP_SERVER_NAME = "research"`, `MAX_TURNS_BACKSTOP`, env loaded from workspace-root `.env` via `Path(__file__).resolve().parents[3]`, `anthropic_key_present()`.

## Step 2 — Schemas (forward-compatible, Phase 1 uses a subset)
- [ ] `src/schemas.py` — dataclasses separating **content from metadata** so provenance survives later:
  - `SourceRef(name, url, excerpt, date)` — `date`/`excerpt` populated now so Phase 4 needs no reshape.
  - `Claim(text, source: SourceRef)`.
  - `SubagentResult(facet, summary, claims: list[Claim], status)` — the ~1–2k-token distilled contract (TR6).
  - `Report(sections, claims, coverage: dict[facet,status], gaps: list)` — Phase 1 fills sections+claims; coverage/gaps stubbed.

## Step 3 — Seeded corpus (full, forward-compatible)
- [ ] `src/mocks/__init__.py`, `src/mocks/corpus.py` — topic **"impact of AI on creative industries"** with 4+ facets: visual art, music, writing, film. Each document = `{id, facet, source, date, url, content}`.
  - (a) 4+ facets covered ✔ (TR4 later).
  - (b) a **conflicting-source pair** on one figure (e.g. adoption %), both credible, different dates.
  - (c) a **differently-dated** source vs. another.
  - (d) a document/endpoint flagged to **time out** (marker only; error behavior wired in Phase 4).
- [ ] Simple `search(query, facet=None) -> list[doc]` retrieval seam over the corpus.

## Step 4 — `web_search` MCP tool
- [ ] `src/tools/__init__.py`, `src/tools/server.py` — `create_sdk_mcp_server` + `@tool("web_search", …)` with a **rich description** (purpose, input format, when-to-use), mirroring sibling tool style.
  - Phase 1: standard content shape, `is_error=False`; returns matched docs with source/date/excerpt fields intact. (Structured errors + timeout are Phase 4 — do not shape them in now, but leave the return envelope roomy.)

## Step 5 — Subagents (`AgentDefinition`s, Sonnet tier)
- [ ] `src/agents/__init__.py`.
- [ ] `src/agents/web_search.py` — `AgentDefinition(model=WORKER_MODEL, mcpServers=[research], tools=["mcp__research__web_search"], prompt=…)`. Prompt states the **output contract**: a distilled summary + structured claim→source→date list; explore in your own window; return only the condensed result (TR6).
- [ ] `src/agents/doc_analysis.py` — `AgentDefinition(model=WORKER_MODEL, tools=["mcp__research__web_search"], prompt=…)`. Receives a document ref + extraction goal *in its prompt* (explicit context, TR2); fetches via the tool; returns structured claims + excerpts + dates.

## Step 6 — Coordinator + run driver
- [ ] `src/coordinator.py`:
  - `build_coordinator_options()` → `ClaudeAgentOptions(model=COORDINATOR_MODEL, system_prompt=…, agents={"web_search":…, "doc_analysis":…}, mcp_servers={research: server}, allowed_tools=["Task", "mcp__research__web_search"], strict_mcp_config=True, max_turns=MAX_TURNS_BACKSTOP)`. **No `tools=[]`.**
  - System prompt: decompose the question into a few subtopics; **delegate** retrieval to `web_search` and document extraction to `doc_analysis` via `Task`, passing all needed context explicitly in each prompt; collect the distilled summaries; **synthesize one basic cited report** yourself (coordinator-owned synthesis).
  - `build_no_task_options()` → same but with `allowed_tools` **omitting `"Task"`** — the negative-test fixture demonstrating a coordinator that cannot delegate.
- [ ] `src/loop.py` — adapt sibling `AgentRun` / `_ingest_message` / `run_turn`; **extend** to capture `Task` tool-use blocks (delegation count + which subagent) so tests assert on structure. Keep the drain-to-`ResultMessage` pattern (no early break) and `terminated_by_cap`.
- [ ] `run_example.py` — load env, `run_research("impact of AI on creative industries")`, print the report + a token-usage line (TR10 groundwork).

## Step 7 — Tests
Unit (default `pytest`, deterministic, free):
- [ ] `test_config.py` — model tiers correct; env path resolves.
- [ ] `test_schemas.py` — round-trip; content/metadata separation holds.
- [ ] `test_corpus.py` — 4+ facets present; the conflicting pair, the dated source, and the timeout marker all exist and are queryable.
- [ ] `test_tools_web_search.py` — tool returns matched docs with source/date/excerpt; `is_error=False`.
- [ ] `test_coordinator_config.py` — **`"Task"` in coordinator `allowed_tools`**; `build_no_task_options()` omits it; both subagents defined; worker models = Sonnet, coordinator = Opus.

Integration (`pytest -m integration`, live, ~1 Opus + 2 Sonnet per run):
- [ ] `test_phase1_spine_live.py`:
  - `Task` fires ≥1; **both** `web_search` and `doc_analysis` were delegated to; a non-empty report is produced; `not run.terminated_by_cap`.
  - **Negative:** with `build_no_task_options()`, `"Task"` never appears in `run.tool_calls` (coordinator cannot delegate) — the acceptance demo, kept as a permanent test behind the marker.

## Validation (Phase 1 done when)  — ✅ ALL PASS
- [x] `pytest` (unit) green and fast (22 passed, ~1.2s); `pytest -m integration` green (3 passed, ~5min).
- [x] Delegation (`Agent`) demonstrably works; subagents receive context via prompt; a full sourced report is produced.
- [x] The no-delegation failure is demonstrable (negative test, `tools=[]`).
- [x] `run_example.py` prints a sectioned, sourced, all-4-facet report end-to-end.

## Notes / open risks
- Step 0 gates everything; if the `allowed_tools`-allowlist recipe doesn't preserve `Task`, fall back to explicitly listing built-ins to keep and re-verify.
- `doc_analysis` sharing the `web_search` tool is a Phase-1 simplification; revisit if Phase 4 provenance needs a distinct fetch path.
- Real model tiers used during dev (Opus coordinator) so decomposition quality isn't masked — flagged for cost awareness.

## Review (Phase 1 — COMPLETE, 2026-07-03)

**Outcome:** The hub-and-spoke spine works end-to-end. A coordinator (Opus) decomposes the
question, delegates to `web_search` + `doc_analysis` subagents (Sonnet) via the `Agent`
tool, and synthesizes a full report spanning all 4 facets with `[source, date]` on every
claim. 22 unit tests + 3 integration tests green. `run_example.py` produces a clean briefing.

**What worked**
- Mirroring the sibling for config/loop/tests was fast and low-risk.
- Task-0 spike-first approach caught the delegation mechanics before writing real code.
- Asserting on structure (`delegations`, `delegated_subagents`, `subtype`, citations) — not prose.
- Seeded corpus engineered up front (conflict pair, dated sources, timeout marker) — the
  live report already surfaced the 40%/55% film figures as a dated time-trend, not a conflict.

**What didn't (and how it was fixed)** — three findings beyond the plan:
1. **The delegation tool is `Agent`, not `Task`** (renamed v2.1.63). `tools=["Agent"]` is the
   working coordinator; `tools=[]` is the negative config. Confirmed via spike; both names
   detected in the stream.
2. **In-process MCP (`create_sdk_mcp_server`) is UNRELIABLE from subagents** — intermittent
   "Stream closed" control-channel races (sometimes every call in a run). `background=False`
   made it worse. **Fix: external stdio MCP server via FastMCP** (`mcp_servers={... "type":"stdio",
   "command": sys.executable, "args":[server.py]}`). This is a deliberate divergence from the
   sibling's in-process pattern and is now 100% reliable. Recorded in memory.
3. **`loop.py` must capture the LAST `ResultMessage`, not the first** — with subagents the
   stream emits several (per-delegation announcements first, coordinator synthesis last), and
   subagent messages carry `parent_tool_use_id` (filtered so only coordinator-level counts).

**Deliberate Phase-1 simplifications (revisit later)**
- Sequential delegation only (steered by prompt); parallel fan-out is Phase 2 and needs its
  own concurrency story (backgrounded parallel `Agent` calls caused the coordinator to end its
  turn with a "launched agents" announcement instead of synthesizing).
- `doc_analysis` reuses the `web_search` tool to fetch by reference; corpus conflict/timeout
  entries are inert data (Phase 3/4 turn them into behavior).

**For Phase 2:** solve awaiting parallel subagents (the crux) — the external server should
handle concurrent calls, but the coordinator's turn-ending-early behavior under parallel
launch is the real problem to design around.

---

# Phase 2 — Parallel Fan-Out + Dynamic Selection (TR2/TR3/TR10)

> Goal: the coordinator spawns subagents that run CONCURRENTLY for broad questions
> (measurably faster than sequential), and a deterministic triage routes narrow lookups to
> a cheap single-agent fallback that skips the ~15× fan-out. Validate on STRUCTURE.

## Scope guardrails (what Phase 2 does NOT do)
- ❌ Scope partitioning + coverage verification + refinement loop (Phase 3, TR4/TR5).
- ❌ Structured error envelopes, conflict/temporal annotation, coverage rendering (Phase 4).
- Corpus timeout marker (D004) stays inert; `Report.coverage`/`gaps` stay stubbed.

## Steps
- [x] Task 1 — `loop.py`: `delegation_batches`, `task_events`, `peak_concurrent_tasks`,
  `max_parallel_delegations`, `subagent_total_tokens`, `total_cost_usd`/`usage`, `route`.
- [x] Task 2 — linchpin spike (ran 3 live variants: background False/None/True + concurrency timing).
- [x] Task 3 — `background=True` on both subagents.
- [x] Task 4 — `src/triage.py` deterministic `classify()`.
- [x] Task 5 — `config.CLASSIFIER_MODEL` (Haiku seam) + `SIMPLE_QUERY_MAX_WORDS`.
- [x] Tasks 6–8 — parallel `SYSTEM_PROMPT`; `_SEQUENTIAL_SYSTEM_PROMPT` +
  `build_sequential_coordinator_options()`; `build_single_agent_options()`; triage-routed
  `run_research()`.
- [x] Tasks 9–10 — `run_example.py` prints route/parallelism/cost; `benchmark_parallel.py`.
- [x] Tasks 11–14 — `test_triage.py`, `test_loop_task_parsing.py`,
  `test_phase2_parallel_live.py`; extended `test_coordinator_config.py`.
- [x] Task 15 — validation, memory, review (this section).

## Validation (Phase 2 done when) — ✅ ALL PASS
- [x] Unit suite green + fast: **57 passed, ~1.1s** (`-m "not integration"`).
- [x] Broad query fans out with REAL concurrency: `peak_concurrent_tasks >= 2` (live test).
- [x] Narrow lookup → single-agent fallback: `route == single_agent`, `delegations == []`,
  no `Agent`, `web_search` used directly (live test).
- [x] Benchmark speedup **1.82×** (sequential 141.9s / peak 1 → parallel 77.9s / peak 4).
- [x] Phase-1 live regression still green under the promoted parallel coordinator.

## Review (Phase 2 — COMPLETE, 2026-07-03)

**Outcome:** Broad questions fan out to concurrent subagents (measured **1.82× faster**,
peak 4 tasks overlapping); narrow lookups route to a cheap grounded single-agent path.
Deterministic triage + loop instrumentation are 100% unit-tested; parallelism and the
fallback are proven live on structure.

**The linchpin spike overturned the plan's core assumption** — this was the whole game:
- The plan chose `max_parallel_delegations >= 2` (≥2 `Agent` blocks in one message) as the
  parallelism proof. **The Opus coordinator NEVER does this** — it emits one `Agent` call
  per message under EVERY `background` setting (False/None/True), even with emphatic
  "single message" steering. So that signal is unreachable; it stays as instrumentation only.
- **Real parallelism = `background=True` + fire delegations back-to-back.** The concurrency
  spike measured **peak 5 tasks active at once**. The deterministic proof is
  `AgentRun.peak_concurrent_tasks` (replay `task_events`: started +1, terminal −1). User
  approved this signal swap. This proves TR2 *better* — real overlap, not just intent.
- The feared "launched agents, will report back" early-finish **never occurred** — the
  coordinator synthesized cleanly inline (num_turns=1, success, citations) in every spike.

**Second finding — the single-agent fallback couldn't reach its tool.** The plan assumed
"MCP tools come via `mcp_servers` regardless of `tools=[]`." False for a top-level
non-delegating agent: it reported "I don't have a web_search tool" and answered from memory
(test failed on `web_search in tool_calls`). **Fix:** the single agent uses an IN-PROCESS
`create_sdk_mcp_server` (the sibling's proven `tools=[]` pattern) — the subagent "Stream
closed" race that forced external stdio doesn't apply with no subagents. Also hardened the
prompt to MANDATE corpus grounding (search first, never answer from memory) and switched the
test lookup to a corpus-only fact ("How many AI music tracks…2024?", D003) so recall can't
substitute for retrieval. Both are correctness improvements, not test-gaming.

**What worked**
- Instrumenting the loop for BOTH paths BEFORE the spike meant the code worked regardless of
  outcome — only the `background` value + prompt cadence + the proof-metric choice changed.
- `peak_concurrent_tasks` from the `task_events` timeline is a clean, non-flaky CI signal;
  the benchmark (kept out of pytest) supplies the wall-clock number on demand.
- Structure-only assertions held up: the fallback failure was caught by `web_search in
  tool_calls`, and the parallelism by `peak_concurrent_tasks`, never by prose.

**Deliberate Phase-2 simplifications (revisit later)**
- Two server flavors now coexist: external stdio (coordinator + subagents) and in-process
  (single-agent fallback). Justified by the surfacing/reliability asymmetry; both share
  `format_search`. Revisit if a later phase unifies them.
- Sequential baseline retained ONLY for the benchmark; `run_research` never takes it.

**For Phase 3:** scope partitioning (assign distinct facets/source-types per subagent to
cut duplicate retrieval) + the refinement loop (evaluate coverage, re-delegate gaps,
re-synthesize up to `MAX_REFINEMENT_ITERATIONS`). `Report.coverage`/`gaps` come alive here.

---

# Phase 3 — Coverage + Refinement (TR4/TR5)

> Goal: the coordinator VERIFIES its report spans the whole topic (kills the "only visual
> arts" trap) and SELF-HEALS an under-covered pass via a code-orchestrated, bounded
> refinement loop. Deep plan: `.agents/plans/phase-3-coverage-refinement.md`.
>
> Confirmed decisions: refinement loop = **code-orchestrated + bounded** (not in-model /
> not sessions); coverage signal = structured **`COVERAGE:` block** parsed by a pure
> evaluator (prose-scan fallback); gap proof = a permanent **partial-coordinator fixture**;
> `run_research` keeps returning `AgentRun` with coverage/gaps/refinement ATTACHED (like `route`).

## Scope guardrails (what Phase 3 does NOT do)
- ❌ Full `schemas.Report` assembly with per-claim `Claim`/`SourceRef` parsing → Phase 4
  (needs claim→source extraction). Phase 3 realizes the coverage/gaps DATA on `AgentRun`.
- ❌ Structured error envelopes, timeout/retry, conflict/temporal annotation, TR9 rendering → Phase 4.
- ❌ Subagent-internal facet-arg capture (tool-level partitioning proof) — deferred (TR6 tension).
  Partitioning is prompt-steered and verified at the REPORT level (coverage spans all facets).
- Corpus timeout marker (D004) stays inert; a residual gap after the cap is left as data (annotated in Phase 4).

## Steps
- [~] Task 1 — prompt-contract spike: FOLDED into Task 12's live test (which is itself the
  contract check) rather than a separate throwaway script — saved a paid run. Contract held
  first try (see review).
- [x] Task 2 — `src/coverage_eval.py`: pure evaluator (`parse_coverage_block`, `evaluate`,
  `canonical_facet`, `facet_mentioned`, alias table, status constants; prose-scan fallback). SDK-free.
- [x] Task 3 — `loop.py`: `AgentRun` fields `refinement_iterations`, `coverage`, `gaps`,
  `coverage_history` (set by `run_research`, not the loop); `@property fully_covered`.
- [x] Task 4 — `coordinator.py`: `SYSTEM_PROMPT` gains one-facet-per-subagent partitioning
  + the `COVERAGE:` block contract (NOT added to `_SEQUENTIAL_SYSTEM_PROMPT`).
- [x] Task 5 — `build_partial_coordinator_options()`: delegation-capable but deliberately
  under-covers (visual art + music only) — permanent live gap fixture.
- [x] Task 6 — `_build_refinement_prompt()` + `_run_with_refinement()`: bounded loop
  (evaluate → re-delegate missing facets with prior draft as context → re-synthesize).
- [x] Task 7 — `run_research()`: route; fan-out path calls `_run_with_refinement(q,
  build_coordinator_options(), corpus.FACETS)`; single-agent path unchanged.
- [x] Task 8 — `run_example.py`: print coverage / gaps / refinement iterations / history.
- [x] Task 9 — `tests/test_coverage.py`: deterministic evaluator table.
- [x] Task 10 — `tests/test_refinement_loop.py`: bounded loop via monkeypatched `run_turn` (no API).
- [x] Task 11 — extend `tests/test_coordinator_config.py`: partial builder + `COVERAGE:` contract.
- [x] Task 12 — `tests/test_phase3_coverage_live.py`: full-coverage happy path + injected-gap refinement.
- [~] Task 13 — this review appended; memory NOT updated (no new SDK mechanic surfaced);
  Phase-1/2 live regression DEFERRED by user (Phase-3 live only, to bound cost).

## Validation (Phase 3 done when) — ✅ CORE PASS (Phase-1/2 live regression deferred)
- [x] Unit suite green + fast: **82 passed, ~1.2s** (57 prior + 25 new; `-m "not integration"`).
- [x] Broad query: `run.coverage` marks all 4 facets covered, `run.gaps == []` (TR4, live PASS).
- [x] Injected gap: partial coordinator → `refinement_iterations >= 1` → final `gaps == []` (TR5, live PASS).
- [x] Loop deterministically bounded by `MAX_REFINEMENT_ITERATIONS` (unit, monkeypatched, no API).
- [ ] Phase-1/2 live regression — DEFERRED by user (ran Phase-3 live only to bound cost). The
  broad path's first turn is unchanged when coverage is full on pass 1 (`refinement_iterations==0`),
  so no behavioral regression is expected. Re-run `pytest -m integration` to confirm when ready.

## Review (Phase 3 — COMPLETE, 2026-07-03)

**Outcome:** The coordinator now VERIFIES coverage and SELF-HEALS gaps. It ends each briefing
with a machine-readable `COVERAGE:` block; a pure evaluator (`coverage_eval.py`) parses it,
alias-maps the free-text labels onto `corpus.FACETS`, and computes gaps. `run_research`'s
fan-out path runs the bounded `_run_with_refinement` loop: on a gap it re-delegates ONLY the
missing facets (prior draft carried as explicit context, TR2) with the full coordinator, up to
`MAX_REFINEMENT_ITERATIONS=2`. 82 unit tests + 2 Phase-3 live tests green.

**Live acceptance (both PASS on the first run, 356s):**
- Broad query → `run.coverage` all 4 facets `covered`, `run.gaps == []` (TR4 — "only visual arts"
  trap detectable and gone).
- Partial coordinator under-covers (visual art + music) → `refinement_iterations >= 1` → final
  `gaps == []`, writing+film now present (TR5 — a real injected gap closed end-to-end).

**What worked**
- The plan's judgment that Phase 3 had NO new SDK mechanic held — it was pure Python
  orchestration + one prompt contract. The prompt contract worked first try (no iteration),
  so the separate Task-1 spike was folded into the live test to save a paid run.
- The pure evaluator + bounded loop were fully unit-tested BEFORE any API call
  (monkeypatched `run_turn` proves stop-on-coverage / iterate-on-gap / cap-bounded /
  `coverage_history` progression). Structure-only assertions throughout.
- `_run_with_refinement` always uses the full coordinator on refinement turns, so the partial
  fixture (an under-covering INITIAL config) is corrected by the full coordinator guided by the
  missing-facet list — a clean way to prove gap-closing without a bespoke recovery path.

**One deliberate deviation from the plan (documented):**
- The alias table drops the bare substrings the plan itself flagged as collision-prone —
  `"video"` (→ "music video"), and by the same reasoning `"art"` (→ "artificial"/"recording
  artists") and `"text"` (→ the visual-art corpus's "text-to-image"). Distinctive aliases
  (`visual`, `illustrat`, `artwork`, `image`, `painting`; `film`/`movie`/`cinema`; etc.) map the
  coordinator's labels without cross-facet false positives. Guarded by a unit test
  (`music video` → music, not film).

**Deliberate Phase-3 boundaries (unchanged, → Phase 4):** full `schemas.Report` assembly with
per-claim `Claim`/`SourceRef` parsing; structured error envelopes + timeout/retry; conflict/
temporal annotation; TR9 coverage rendering by content type. The corpus timeout marker (D004)
stays inert; a residual gap after the cap is left as data.

**For Phase 4:** wire the seeded corpus's conflict pair (D007/D008, 40% vs 55%), dated sources,
and timeout marker (D004) into real behavior — structured error propagation (retry vs. valid
empty), claim→source provenance, conflict/temporal annotation, and TR9 coverage rendering.
