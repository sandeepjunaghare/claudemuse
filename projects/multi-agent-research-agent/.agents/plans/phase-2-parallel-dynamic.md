# Feature: Phase 2 — Parallel Fan-Out + Dynamic Selection (TR2, TR3, TR10)

The following plan should be complete, but it is **important that you validate documentation
and codebase patterns and task sanity before you start implementing.** In particular, **Task 1
is a mandatory empirical spike** whose outcome selects between two committed implementation
paths — do NOT skip it, and do NOT write the parallel coordinator before it resolves.

Pay special attention to the naming of existing utils, types, and models (`AgentRun`,
`SubagentResult`, `build_*_options`, `_bare_tool_name`, `config.WORKER_MODEL`). Import from the
right files — this project uses **flat absolute imports** off `src/` (`import config`,
`from loop import run_turn`), wired by `tests/conftest.py` and `run_example.py` inserting `src/`
on `sys.path`. Do not introduce package-relative imports.

## Feature Description

Phase 1 delivered a working hub-and-spoke spine where the coordinator delegates to `web_search`
and `doc_analysis` **sequentially** (one `Agent` call at a time, steered by the system prompt)
and then synthesizes a cited briefing. Phase 2 adds the two capabilities that justify the
multi-agent architecture's ~15× cost:

1. **Parallel fan-out (TR2/FR3):** the coordinator emits **multiple `Agent` delegations in a
   single response** so subagents explore concurrently, making a broad multi-subtopic query
   return in ≈ the slowest subagent's time rather than the sum. This must be **measurably
   faster** than the Phase-1 sequential path on a 3-subtopic query.
2. **Dynamic selection (TR3/TR10):** a **deterministic triage classifier** inspects each
   question and routes it. A **broad** question takes the full parallel fan-out; a **narrow
   lookup** takes a cheap **single-agent fallback** that answers directly (no delegation, no
   15× cost).

Everything is validated on **structure** (which subagents ran, whether they ran in one turn,
which route was taken), never on the model's prose — the house ethos.

## User Story

As a **builder/maintainer of the research system**
I want the coordinator to **spawn subagents in parallel for broad questions and skip the fan-out
entirely for narrow lookups**
So that **a multi-subtopic briefing returns measurably faster than sequential delegation, and a
simple fact lookup does not pay the ~15× multi-agent cost.**

Supporting stories from the PRD (§5): #6 (parallel spawning measurably beats sequential), #7
(narrow queries skip the full pipeline), #8 (token metrics defend the architecture).

## Problem Statement

- Phase 1's coordinator delegates **sequentially** by explicit prompt instruction ("send ONE
  subagent at a time, wait…"). On a topic with 4 facets this serializes 4 subagent round-trips —
  slow, and it hides the core value proposition of multi-agent (parallelism). The PRD acceptance
  criterion **"parallel spawning measurably beats sequential on a 3-subtopic query"** is unmet.
- The system runs the **full fan-out for every query**, including narrow lookups
  ("What year was Stable Diffusion released?"). That pays ~15× cost for a single fact — the exact
  anti-pattern TR3/TR10 exist to prevent. There is no single-agent fallback path.
- **The linchpin technical risk** (flagged in `_tasks/todo.md` Phase-1 review and memory
  `mar-agent-sdk-delegation`): emitting multiple `Agent` calls in one turn runs them
  **in the background by default** on recent CLIs, and the coordinator has been observed to end
  its turn with a *"I've launched the agents, will report back"* announcement **instead of
  synthesizing**. Phase 2 must design around this, not wish it away.

## Solution Statement

- **Spike-first (Task 1):** empirically pin the SDK's parallel-delegation runtime on the
  installed `claude-agent-sdk` 0.2.110 + current CLI. Determine whether setting
  `AgentDefinition(background=False)` + a "emit all delegations in one message, then synthesize"
  system prompt yields subagent results **inline in the same turn** (**Path A**), or whether
  subagents run in the background and results arrive as `TaskNotification`/`TaskUpdated` system
  messages (**Path B**). Commit to whichever the spike confirms. Record the recipe in
  `coordinator.py` and update memory `mar-agent-sdk-delegation`.
- **Parallel coordinator:** promote `build_coordinator_options()` to steer **parallel** fan-out
  (all `Agent` calls in one message). Retain the Phase-1 sequential prompt as
  `build_sequential_coordinator_options()` — the **benchmark baseline** only.
- **Deterministic triage (`src/triage.py`):** a pure function `classify(question) -> route`
  using breadth-vs-lookup heuristics. 100% unit-testable without an API call. Leaves a documented
  seam to swap in a Haiku LLM classifier later (PRD §6's suggestion, deferred).
- **Single-agent fallback:** `build_single_agent_options()` — Sonnet, **no `Agent` tool, no
  subagents**, but keeps the `web_search` MCP tool so it answers narrow questions directly.
  `run_research()` routes via `triage.classify`.
- **Instrumentation:** extend `loop.py`/`AgentRun` to capture (a) **delegation batches** (which
  subagents were delegated *in the same assistant message* → the deterministic parallelism
  signal), (b) **Task lifecycle events** with per-subagent `duration_ms`/`total_tokens` (Path B
  support + TR10 token accounting), and (c) the chosen **route**.
- **Proof:** a permanent deterministic test asserts `run.max_parallel_delegations >= 2` for broad
  queries and `run.route == single-agent` for lookups; a standalone **benchmark script**
  (`benchmark_parallel.py`) prints the sequential-vs-parallel wall-clock number on demand
  (kept out of pytest to avoid timing flakiness — per the confirmed decision).

## Feature Metadata

**Feature Type:** Enhancement (extends the Phase-1 spine)
**Estimated Complexity:** **Medium–High** — the logic is modest, but the SDK parallel-execution
runtime is a real unknown that the spike must resolve; the wrong assumption invalidates the
coordinator design.
**Primary Systems Affected:** `src/coordinator.py`, `src/loop.py`, `src/agents/*.py`, new
`src/triage.py`, `run_example.py`, new `benchmark_parallel.py`, `tests/`.
**Dependencies:** No new packages. Uses existing `claude-agent-sdk` 0.2.110 message types
(`TaskStartedMessage`, `TaskProgressMessage`, `TaskNotificationMessage`, `TaskUpdatedMessage`,
`TERMINAL_TASK_STATUSES`, `TaskUsage`) — all already exported from the top-level `claude_agent_sdk`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING!

- `src/coordinator.py` (whole file, ~143 lines) — **Why:** the hub. You will (a) rewrite
  `SYSTEM_PROMPT` for parallel steering, (b) keep the Phase-1 sequential prompt as a baseline
  builder, (c) add `build_single_agent_options()`, (d) route `run_research()` through triage.
  Note the verified delegation recipe in its module docstring (lines 6–21) — `tools=["Agent"]`
  keeps ONLY delegation; `allowed_tools` MUST also list `mcp__research__web_search`; the MCP
  server is **external stdio**.
- `src/loop.py` (whole file, 154 lines) — **Why:** you extend `AgentRun` + `_ingest_message`.
  Critical existing behaviors to preserve: coordinator-level filter `parent_tool_use_id is None`
  (lines 97–101, TR6 isolation); keep the **LAST** `ResultMessage` (lines 118–128); drain the
  stream to completion, never `break` (lines 141–149, comment explains the `aclose()` hazard);
  `_DELEGATION_TOOL_NAMES = ("Agent", "Task")` (line 43); `_bare_tool_name` (lines 49–55).
- `src/agents/web_search.py` + `src/agents/doc_analysis.py` (both ~45 lines) — **Why:** you add
  the `background=...` field decided by the spike. Keep prompts **benign/research-framed** (org
  guardrail gotcha — see memory). Both already declare `tools=[_WEB_SEARCH_TOOL]` and
  `mcpServers=[config.MCP_SERVER_NAME]`.
- `src/config.py` (58 lines) — **Why:** add the Haiku model constant (for the future classifier
  seam / model tiering completeness) and any triage tuning constants. `COORDINATOR_MODEL` =
  Opus, `WORKER_MODEL` = Sonnet already defined (lines 18/22). `.env` path via
  `parents[3]` (line 41) — do not change.
- `src/schemas.py` (68 lines) — **Why:** reference only. `SubagentResult`/`Report`/`Claim`/
  `SourceRef` unchanged in Phase 2 (provenance shaping is Phase 4). Do not reshape them.
- `tests/conftest.py` (61 lines) — **Why:** the fixture pattern (`run_research`,
  `run_no_delegation` — lazy SDK import inside fixtures so the deterministic suite never imports
  the SDK). You will add a `run_single_agent`-style fixture and possibly a parallel fixture.
  `agent_runnable()` (lines 26–34) gates live tests on `claude` CLI or `ANTHROPIC_API_KEY`.
- `tests/test_coordinator_config.py` (43 lines) — **Why:** the unit pattern for option
  construction (no API call). You extend it for single-agent + parallel + sequential builders.
- `tests/test_phase1_spine_live.py` (85 lines) — **Why:** the integration-test shape you mirror
  for Phase 2 live tests. Note `_FACET_KEYWORDS` lenient breadth signal (line 30), the
  citation-bracket guard against the "launched agents" false positive (line 56), and the
  `pytestmark = [pytest.mark.integration, pytest.mark.skipif(...)]` gate (lines 19–25).
- `run_example.py` (30 lines) — **Why:** you extend the printed summary to show route +
  max-parallel-delegations + token/cost (TR10). Mirror its structure for `benchmark_parallel.py`.
- `_tasks/todo.md` (whole file) — **Why:** Phase-1 review + the Phase-2 handoff note (lines
  121–124): *"solve awaiting parallel subagents (the crux)… the coordinator's turn-ending-early
  behavior under parallel launch is the real problem to design around."* This plan is that solve.

### Installed-SDK reference (READ to confirm field names — do not trust paraphrase)

- `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/lib/python3.10/site-packages/claude_agent_sdk/types.py`
  - `AgentDefinition` — line 83; **`background: bool | None = None`** at **line 99**.
  - `TaskUsage` (TypedDict `{total_tokens, tool_uses, duration_ms}`) — line 1047.
  - `TaskNotificationStatus = Literal["completed","failed","stopped"]` — line 1056.
  - `TERMINAL_TASK_STATUSES = frozenset({"completed","failed","stopped","killed"})` — line 1074.
  - `TaskStartedMessage` (`task_id, description, uuid, session_id, tool_use_id?, task_type?`) — 1080.
  - `TaskProgressMessage` (`+ usage: TaskUsage, last_tool_name?`) — 1097.
  - `TaskNotificationMessage` (`task_id, status, output_file, summary, uuid, session_id,
    tool_use_id?, usage: TaskUsage|None`) — 1115. **`.summary` = the subagent's final result text;
    `.tool_use_id` back-references the spawning `Agent` block.**
  - `TaskUpdatedMessage` (`task_id, patch: dict, status: TaskUpdatedStatus|None, session_id?,
    uuid?`) — 1140. **Terminal state may arrive ONLY here (no notification) — clear active tasks on
    a terminal status from EITHER message.**
  - `ResultMessage` (`subtype, duration_ms, duration_api_ms, is_error, num_turns, session_id,
    stop_reason?, total_cost_usd?, usage?, result?, model_usage?, …`) — line 1200.
- `_internal/message_parser.py` lines 189–252 — the `system`/`task_*` parse cases (confirms the
  exact `data[...]` keys and that all four Task messages are typed subclasses of `SystemMessage`).
- All Task types are exported from the package root — `from claude_agent_sdk import
  TaskNotificationMessage, TaskUpdatedMessage, TaskStartedMessage, TaskProgressMessage,
  TERMINAL_TASK_STATUSES` (see `__init__.py` lines 130–137, 548–555).

### New Files to Create

- `src/triage.py` — deterministic query classifier (`classify()` + route constants). SDK-free,
  unit-testable without credentials (mirror `schemas.py`/`mocks/corpus.py` SDK-free style).
- `benchmark_parallel.py` (project root, next to `run_example.py`) — standalone script that times
  the sequential vs parallel coordinator on a 3-subtopic question and prints the speedup + tokens.
  NOT a pytest test.
- `tests/test_triage.py` — deterministic unit table for `classify()`.
- `tests/test_loop_task_parsing.py` — deterministic unit test feeding synthetic
  `AssistantMessage` (multi-`ToolUseBlock`) + `Task*Message` objects through `_ingest_message`
  and asserting `delegation_batches`, `max_parallel_delegations`, and `task_events`. No API call.
- `tests/test_phase2_parallel_live.py` — integration (`-m integration`): broad query fans out in
  parallel; simple query takes the single-agent fallback.

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- Agent SDK — Subagents: https://platform.claude.com/docs/en/agent-sdk/subagents
  - Section: parallel subagent invocation / `run_in_background` semantics. **Why:** the documented
    behavior is that omitting `run_in_background` launches a **background** subagent on current
    CLIs, and the model sets `run_in_background: false` when it needs the result inline. This is
    exactly what the Task-1 spike must confirm against the installed version.
- Agent SDK — Sessions: https://platform.claude.com/docs/en/agent-sdk/sessions
  - **Why:** background-task lifecycle + `task_notification` semantics referenced in
    `client.py:453` docstring.
- Anthropic — "How we built our multi-agent research system"
  - **Why:** the canonical justification for parallel fan-out + cost framing (TR10 writeup).
- Memory `mar-agent-sdk-delegation` (already in your context) — **Why:** the verified Phase-1
  recipe and the explicit Phase-2 warning about background/premature-turn-end. Update it with the
  spike's Phase-2 finding.

### Patterns to Follow

**Route/status constants (mirror the string-status style in `schemas.py`/`corpus.py`):**
```python
# src/triage.py
ROUTE_SINGLE_AGENT = "single_agent"   # narrow lookup → cheap fallback, no fan-out
ROUTE_FAN_OUT = "fan_out"             # broad question → parallel multi-agent
```

**Option-builder pattern (mirror `coordinator.py:99-137`):** each `build_*_options()` returns a
fully-formed `ClaudeAgentOptions`; the working config sets `tools=["Agent"]`; the "cannot
delegate" configs set `tools=[]`. MCP tool always in `allowed_tools`; `strict_mcp_config=True`;
`max_turns=config.MAX_TURNS_BACKSTOP`.

**AgentRun assertion surface (mirror `loop.py:58-85`):** add new fields as `field(default_factory=...)`,
add derived signals as `@property`. Tests assert on these, never on prose.

**Test split (mirror `conftest.py` + `test_phase1_spine_live.py`):** deterministic units import
nothing SDK-backed at collection time (lazy imports in fixtures); live tests carry
`pytestmark = [pytest.mark.integration, pytest.mark.skipif(not agent_runnable(), ...)]`.

**Docstring density (mirror every existing `src/*.py`):** each module opens with a docstring
tying the code to its TR(s) and noting deliberate simplifications. Match it.

---

## IMPLEMENTATION PLAN

### Phase 1 (Foundation): De-risk the parallel-execution runtime — the linchpin spike

Resolve HOW parallel `Agent` fan-out returns results before designing the coordinator. This is
the direct analog of Phase-1's Task-0 spike. Build the `loop.py` instrumentation first (it is
needed by BOTH paths and by the spike itself), then run the throwaway spike, then commit to a path.

**Tasks:** extend `AgentRun`/`_ingest_message` to capture delegation batches + Task events →
write a throwaway spike script → decide Path A (inline) vs Path B (background) → record the recipe.

### Phase 2 (Core Implementation): Parallel coordinator + deterministic triage + single-agent fallback

Rewrite the coordinator system prompt for parallel steering; keep the sequential prompt as the
benchmark baseline; add `triage.py`; add `build_single_agent_options()`; route `run_research()`.

### Phase 3 (Integration): Wire routing, instrumentation, and the runnable surfaces

`run_research()` triage routing; `AgentRun.route` set; `run_example.py` prints route + parallelism
+ tokens; `benchmark_parallel.py` created.

### Phase 4 (Testing & Validation): Deterministic units + live integration + benchmark

Unit tables for triage and loop parsing; live tests for parallel fan-out and single-agent
fallback; run the benchmark to capture the real speedup number.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently
testable. Tasks 1–3 (instrumentation + spike) gate everything after them.

### Task 1 — UPDATE `src/loop.py`: capture delegation batches + Task lifecycle events

- **IMPLEMENT:**
  - Add imports from `claude_agent_sdk`: `TaskStartedMessage, TaskProgressMessage,
    TaskNotificationMessage, TaskUpdatedMessage, TERMINAL_TASK_STATUSES`.
  - New `AgentRun` fields (all `field(default_factory=list)` / `None`):
    - `delegation_batches: list[list[str]]` — one entry per **coordinator assistant message that
      contained ≥1 delegation**; the entry is the list of `subagent_type`s delegated in that single
      message. This is the deterministic parallelism signal.
    - `task_events: list[dict]` — one dict per `Task*Message` seen: `{"kind": <"started"|
      "progress"|"notification"|"updated">, "task_id", "tool_use_id", "status", "total_tokens",
      "duration_ms"}` (missing values `None`). `total_tokens`/`duration_ms` pulled from
      `TaskUsage` when present (`.usage["total_tokens"]`, `.usage["duration_ms"]`).
    - `route: str | None = None` — set by `run_research()` (Task 8), not by the loop.
    - `total_cost_usd: float | None = None` and `usage: dict | None = None` — captured from the
      last `ResultMessage` (TR10).
  - New `@property max_parallel_delegations` → `max((len(b) for b in delegation_batches),
    default=0)`.
  - New `@property fanned_out_in_parallel` → `self.max_parallel_delegations >= 2`.
  - New `@property subagent_total_tokens` → sum of `e["total_tokens"] or 0` for task_events with
    `kind == "notification"` (TR10 subagent cost).
  - In `_ingest_message`, for a **coordinator-level** `AssistantMessage` (existing
    `parent is None` branch): after the per-block loop, if any delegation blocks were seen in THIS
    message, append their `subagent_type`s (in order) as ONE list to `run.delegation_batches`.
    (Keep the existing per-delegation append to `run.delegations` unchanged.)
  - Add handling for the four `Task*Message` types (they are `SystemMessage` subclasses; match
    them explicitly BEFORE any generic system handling). Record into `run.task_events`. Do NOT
    gate these on `parent_tool_use_id` (they are the lifecycle mechanism, not subagent-internal
    tool calls). Extract `duration_ms`/`total_tokens` defensively (`usage` may be `None` on
    notification; absent entirely on started/updated).
  - In the `ResultMessage` branch, also capture `run.total_cost_usd = getattr(message,
    "total_cost_usd", None)` and `run.usage = getattr(message, "usage", None)`.
- **PATTERN:** `src/loop.py:88-128` (existing `_ingest_message` structure, coordinator-level
  filter, last-ResultMessage overwrite).
- **IMPORTS:** `from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage,
  TextBlock, ToolUseBlock, query, TaskStartedMessage, TaskProgressMessage,
  TaskNotificationMessage, TaskUpdatedMessage, TERMINAL_TASK_STATUSES)`.
- **GOTCHA:** `TaskUsage` is a **TypedDict**, so access with `usage["duration_ms"]` (subscript),
  guarded by `if usage:`. `TaskUpdatedMessage.status` can be `None` (non-terminal patch). Don't
  assume every task emits a `notification` — a killed/stopped task may only emit `task_updated`
  (see types.py:1148-1154). The existing "keep LAST ResultMessage, drain the stream, never break"
  invariants MUST survive this edit.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import loop;
  r=loop.AgentRun(); print(r.max_parallel_delegations, r.fanned_out_in_parallel,
  r.subagent_total_tokens)"` → prints `0 False 0`.

### Task 2 — CREATE `scratchpad` spike script to pin the parallel runtime  ⚠️ linchpin

- **IMPLEMENT:** a throwaway script (put it under the session scratchpad, NOT the repo) that:
  1. Builds a minimal coordinator with BOTH subagents and a system prompt that says: *"Decide the
     facets up front, then emit ALL your `Agent` delegations in a SINGLE message so they run
     concurrently. After their results return, synthesize one cited briefing. Do NOT end your turn
     with a 'launched agents, will report back' message."*
  2. Runs it once with subagents set `background=False` and once with `background=None` (default),
     on a 3-facet question.
  3. Prints, per run: `run.delegation_batches`, `run.max_parallel_delegations`, `len(run.tool_calls)`,
     `run.num_turns`, `run.subtype`, whether `run.final_text` contains a citation bracket,
     `len(run.task_events)` and the distinct `kind`s seen, and `run.total_cost_usd`.
- **DECISION RULE:**
  - **Path A (inline, PREFERRED — least divergence from Phase 1):** if with `background=False`
    the run shows `max_parallel_delegations >= 2` **and** `subtype == "success"` **and**
    `final_text` has citations (i.e., the coordinator synthesized inline in the same query) →
    adopt Path A. Subagent results returned inline as tool results; `task_events` may be empty.
  - **Path B (background):** if the coordinator ends early (no citations, few tool_calls, task
    results only in `task_events` as `notification`/`updated`) → adopt Path B: rely on the
    coordinator getting a follow-up synthesis turn once tasks reach `TERMINAL_TASK_STATUSES`, and
    surface subagent summaries from `TaskNotificationMessage.summary`. If even that fails, fall
    back to prompt-forcing `run_in_background:false` via stronger steering, and document it.
- **PATTERN:** mirror `run_example.py` for the run/print scaffold; import from `coordinator`/`loop`.
- **GOTCHA:** keep subagent prompts benign/research-framed (org guardrail trips on
  "reveal/secret"-style prompts — memory `mar-agent-sdk-delegation`). This costs real API calls —
  run it ONCE, capture output, delete the script.
- **VALIDATE:** run it: `../../.venv/bin/python <scratchpad>/spike_parallel.py` — read output,
  record which Path is confirmed. **Write the confirmed recipe as a comment block in
  `coordinator.py` and update memory `mar-agent-sdk-delegation`.**

### Task 3 — UPDATE `src/agents/web_search.py` and `src/agents/doc_analysis.py`: set `background` per spike

- **IMPLEMENT:** add `background=False` (Path A) or `background=True` (Path B) to BOTH
  `AgentDefinition(...)` calls, matching the Task-2 decision. Add a one-line comment citing the
  spike. No prompt changes otherwise (keep the distilled-summary output contract).
- **PATTERN:** `src/agents/web_search.py:18-45` (AgentDefinition kwargs order).
- **IMPORTS:** none new.
- **GOTCHA:** `background` is a real field (`types.py:99`); an unknown kwarg would raise at import
  — validate by importing.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from
  agents.web_search import web_search_agent; from agents.doc_analysis import doc_analysis_agent;
  print(web_search_agent.background, doc_analysis_agent.background)"` → prints the chosen value
  for both.

### Task 4 — CREATE `src/triage.py`: deterministic query classifier (TR3)

- **IMPLEMENT:**
  - Module docstring tying to TR3/TR10 and noting the deferred Haiku-classifier seam.
  - `ROUTE_SINGLE_AGENT = "single_agent"`, `ROUTE_FAN_OUT = "fan_out"`.
  - `classify(question: str) -> str` — pure, deterministic, no API. Heuristic:
    - Normalize: lowercase, strip.
    - **Lookup signals → SINGLE_AGENT:** short (≤ `SIMPLE_MAX_WORDS`, e.g. 12 words) AND matches a
      single-fact interrogative pattern — starts with / contains one of `what year`, `when did`,
      `when was`, `who`, `how many`, `how much`, `release date`, `define`, `what is the` +
      no breadth marker.
    - **Breadth signals → FAN_OUT:** contains any of `impact`, `effect`, `landscape`, `overview`,
      `state of`, `trends`, `compare`, `comparison`, ` vs `, `across`, `implications`, `pros and
      cons`, or has multiple coordinated clauses (contains ` and ` joining topic nouns, or a
      comma-separated list of ≥2 facets), OR is long (> `SIMPLE_MAX_WORDS`).
    - **Default:** if neither strongly matches, default to `ROUTE_FAN_OUT` (safer to over-cover
      than to under-cover — the canonical failure is missing breadth; a false FAN_OUT costs
      tokens but never misleads). Document this bias in the docstring.
  - Keep the heuristic small and readable; expose the marker word-lists as module constants so the
    unit test and future tuning share one source of truth.
- **PATTERN:** SDK-free pure module like `src/mocks/corpus.py` (functions + module-level data,
  no SDK import). camelCase is NOT used here — the repo is Python `snake_case` (global style says
  camelCase, but MATCH THE CODEBASE, which is snake_case throughout; the global rule yields to the
  project convention).
- **IMPORTS:** stdlib only (`re` if useful). No SDK, no config needed unless you place
  `SIMPLE_MAX_WORDS` in `config.py` (optional — see Task 5).
- **GOTCHA:** the classifier must be **total and deterministic** (never raise, same input → same
  output) so the unit table is stable. Do not call any model here.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import triage;
  print(triage.classify('What year was Stable Diffusion released?'),
  triage.classify('What is the impact of AI on creative industries?'))"` →
  prints `single_agent fan_out`.

### Task 5 — UPDATE `src/config.py`: add Haiku tier constant (+ optional triage constant)

- **IMPLEMENT:** add `CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"` with a comment: "trivial
  classification tier (TR3); UNUSED by the deterministic triage in Phase 2 — defined now as the
  single source of truth for the deferred LLM-classifier seam." Optionally add
  `SIMPLE_QUERY_MAX_WORDS = 12` if `triage.py` reads it from config.
- **PATTERN:** `src/config.py:14-36` (constants with TR-tagged comments; `MAX_REFINEMENT_ITERATIONS`
  is the precedent for a "defined now, unused until later phase" constant).
- **IMPORTS:** none.
- **GOTCHA:** use the exact Haiku model id from the environment note (`claude-haiku-4-5-20251001`).
  Do not invent an alias.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config;
  print(config.CLASSIFIER_MODEL)"` → prints `claude-haiku-4-5-20251001`.

### Task 6 — UPDATE `src/coordinator.py`: parallel system prompt + keep sequential baseline

- **IMPLEMENT:**
  - Rewrite `SYSTEM_PROMPT` (the module-level default) to steer **parallel** fan-out. Keep every
    non-negotiable from Phase 1 (decompose into facets covering the whole topic; use BOTH
    subagents; pass ALL context explicitly; every claim carries `[source, date]`; do NOT end the
    turn until the full synthesized briefing is written; prefer subagents' findings). CHANGE the
    delegation instruction from "SEQUENTIALLY and WAIT, one at a time" to: *"Decide all the facets
    up front, then emit ALL your `Agent` delegations in a SINGLE message so the subagents run
    concurrently. Once their distilled results have returned, synthesize ONE cited briefing.
    Never end your turn with a 'launched agents, will report back' message."* (Fold in any extra
    steering the spike proved necessary.)
  - Preserve the Phase-1 sequential prompt verbatim as a new module constant
    `_SEQUENTIAL_SYSTEM_PROMPT` (copy the current text). Add
    `build_sequential_coordinator_options()` returning the same options as
    `build_coordinator_options()` but with `system_prompt=_SEQUENTIAL_SYSTEM_PROMPT`. Docstring:
    "Phase-1 sequential baseline — retained ONLY as the benchmark comparison in
    `benchmark_parallel.py`. Not the default path."
  - `build_coordinator_options()` stays the **parallel default** (same tools/agents/mcp/allowed_tools
    as Phase 1; only the prompt changed).
  - Keep `build_no_delegation_options()` unchanged.
- **PATTERN:** `src/coordinator.py:58-137`.
- **IMPORTS:** none new.
- **GOTCHA:** existing `tests/test_coordinator_config.py` asserts on `tools`/`allowed_tools`/
  `agents`/`model` — those are UNCHANGED, so it must still pass. The Phase-1 live test
  (`test_phase1_spine_live.py`) asserts ≥2 delegations, both subagents, clean finish, citations —
  the parallel coordinator still satisfies all of these (verify it still passes under
  `-m integration`).
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from coordinator
  import build_coordinator_options, build_sequential_coordinator_options; a=build_coordinator_options();
  b=build_sequential_coordinator_options(); print(a.tools, sorted(a.agents), a.system_prompt !=
  b.system_prompt)"` → prints `['Agent'] ['doc_analysis', 'web_search'] True`.

### Task 7 — ADD `build_single_agent_options()` to `src/coordinator.py` (TR3/TR10 fallback)

- **IMPLEMENT:** a builder for the cheap narrow-lookup path:
  - `model=config.WORKER_MODEL` (Sonnet — no Opus coordinator needed for a lookup).
  - `tools=[]` (strips the `Agent` tool → **cannot delegate**, structurally guaranteeing no
    fan-out), `agents={}` (no subagents).
  - `mcp_servers=_research_mcp_config()`, `allowed_tools=[_WEB_SEARCH_TOOL]` (MCP tools come via
    `mcp_servers` independent of the `--tools` base set — memory-confirmed — so `web_search` is
    still available even with `tools=[]`).
  - `strict_mcp_config=True`, `max_turns=config.MAX_TURNS_BACKSTOP`.
  - A focused system prompt: *"Answer this narrow, specific question DIRECTLY. Use the `web_search`
    tool yourself to find the fact, then answer concisely with the source and date inline as
    `[source, date]`. Do not attempt to delegate — you are a single agent."*
- **PATTERN:** `src/coordinator.py:120-137` (`build_no_delegation_options` is the structural twin —
  `tools=[]`, no agents — differing only in model=Sonnet and the direct-answer prompt).
- **IMPORTS:** none new.
- **GOTCHA:** do NOT list `"Agent"` in `allowed_tools` here (it isn't in the base set anyway, but
  keep the config honest). This path's whole point is that `run.delegations == []`.
- **VALIDATE:** `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from coordinator
  import build_single_agent_options as f; o=f(); print(o.tools, o.model, 'Agent' not in
  (o.allowed_tools or []), not o.agents)"` → prints `[] claude-sonnet-4-6 True True`.

### Task 8 — UPDATE `run_research()` in `src/coordinator.py`: triage routing

- **IMPLEMENT:** route via triage and stamp the route on the returned run:
  ```python
  import triage
  async def run_research(question: str) -> AgentRun:
      route = triage.classify(question)
      options = (build_single_agent_options() if route == triage.ROUTE_SINGLE_AGENT
                 else build_coordinator_options())
      run = await run_turn(question, options)
      run.route = route
      return run
  ```
- **PATTERN:** `src/coordinator.py:140-142` (current `run_research`).
- **IMPORTS:** `import triage` at module top (flat import; `src/` is on the path).
- **GOTCHA:** `run.route` is set AFTER `run_turn` returns (the loop doesn't know the route). Keep
  `run_turn` route-agnostic.
- **VALIDATE:** covered by Task 11 unit test + Task 13 live tests (no cheap standalone check —
  `run_research` makes API calls).

### Task 9 — UPDATE `run_example.py`: show route + parallelism + tokens (TR10)

- **IMPLEMENT:** extend the printout with `run.route`, `run.max_parallel_delegations`,
  `run.delegation_batches`, and `run.total_cost_usd` / `run.subagent_total_tokens`. Keep the
  existing lines.
- **PATTERN:** `run_example.py:18-26`.
- **VALIDATE:** `../../.venv/bin/python run_example.py` (integration; requires CLI/API) — prints a
  report with `ROUTE: fan_out`, `MAX PARALLEL DELEGATIONS: >=2`, and a cost line.

### Task 10 — CREATE `benchmark_parallel.py` (project root): sequential vs parallel wall-clock

- **IMPLEMENT:** a standalone async script (NOT a pytest test) that:
  - Uses a fixed 3-subtopic question (e.g. the canonical creative-industries question, which
    triages to `fan_out`).
  - Times `run_turn(q, build_sequential_coordinator_options())` and `run_turn(q,
    build_coordinator_options())` with `time.perf_counter()`.
  - Prints for each: wall-clock seconds, `num_turns`, `max_parallel_delegations`,
    `len(delegations)`, `subtype`, `total_cost_usd`, `subagent_total_tokens`.
  - Prints the **speedup** (`sequential_s / parallel_s`) and a one-line verdict.
- **PATTERN:** mirror `run_example.py` scaffold (`sys.path.insert(0,'src')`, `config.load_env()`,
  `asyncio.run(main())`).
- **IMPORTS:** `import asyncio, time, sys`; `from coordinator import
  build_coordinator_options, build_sequential_coordinator_options`; `from loop import run_turn`.
- **GOTCHA:** this costs ~2 full Opus+Sonnet research runs — it is a manual, on-demand tool, not
  CI. Note that in a header comment. Parallel should win, but a single slow API sample is not a
  test — that's exactly why it's a script (per the confirmed decision).
- **VALIDATE:** `../../.venv/bin/python benchmark_parallel.py` — prints both timings and a speedup
  > 1.0 (record the number in the todo review).

### Task 11 — CREATE `tests/test_triage.py`: deterministic classifier table (unit)

- **IMPLEMENT:** a parametrized table of `(question, expected_route)` covering:
  - SINGLE_AGENT: "What year was Stable Diffusion released?", "When did Midjourney launch?",
    "Who created DALL·E?", "How many AI music tracks were produced in 2024?", "Define generative
    AI." (short, single-fact).
  - FAN_OUT: the canonical "What is the impact of AI on creative industries?", "Compare AI adoption
    in film vs music", "Give an overview of AI's effect on writing, art, and film", "State of AI
    in the creative economy", and a long multi-clause question.
  - Edge/default: an ambiguous medium question → assert it defaults to `FAN_OUT` (documents the
    safe-bias). At least 12 cases total; guardrail cases (both canonical extremes) must be exact.
- **PATTERN:** `customer-support/tests/test_hooks_refund_gate.py` boundary-table style +
  `test_handoff.py` pure-function assertions (no SDK, no API).
- **IMPORTS:** `import triage` (conftest puts `src/` on path); `import pytest`.
- **GOTCHA:** these run in the DEFAULT suite (no `integration` marker) — must not import the SDK.
  `triage` is SDK-free, so this is clean.
- **VALIDATE:** `../../.venv/bin/pytest tests/test_triage.py -q` → all pass, <1s.

### Task 12 — CREATE `tests/test_loop_task_parsing.py`: instrumentation parsing (unit, no API)

- **IMPLEMENT:** construct synthetic messages and drive `loop._ingest_message` directly:
  - An `AssistantMessage` (with `parent_tool_use_id=None`) whose `content` has TWO
    `ToolUseBlock`s named `"Agent"` (inputs `{"subagent_type":"web_search","prompt":"..."}` and
    `{"subagent_type":"doc_analysis","prompt":"..."}`) → assert after ingest:
    `run.delegation_batches == [["web_search","doc_analysis"]]`, `run.max_parallel_delegations ==
    2`, `run.fanned_out_in_parallel is True`, and `run.delegations` has 2 entries (existing surface
    intact).
  - A `TaskNotificationMessage(status="completed", summary="...", usage={"total_tokens":1234,
    "tool_uses":3,"duration_ms":5000}, ...)` → assert a `task_events` entry with
    `kind=="notification"`, `total_tokens==1234`, `duration_ms==5000`; and
    `run.subagent_total_tokens == 1234`.
  - A `TaskUpdatedMessage(patch={"status":"killed"}, status="killed", ...)` → assert it is
    recorded and its status is in `TERMINAL_TASK_STATUSES`.
  - A subagent-internal `AssistantMessage` (`parent_tool_use_id="abc"`) with a tool block →
    assert it is IGNORED (no new `tool_calls`, no new batch) — TR6 isolation preserved.
- **PATTERN:** `customer-support/tests/test_hooks_prerequisite_gate.py` (direct call with synthetic
  input shapes, no SDK run). Build the SDK dataclasses directly — they're importable and cheap to
  construct.
- **IMPORTS:** `from claude_agent_sdk import AssistantMessage, ToolUseBlock, TaskNotificationMessage,
  TaskUpdatedMessage, ResultMessage, TERMINAL_TASK_STATUSES`; `import loop`.
- **GOTCHA:** this imports the SDK at collection time (constructing the dataclasses), so it is a
  **light SDK-touching unit test** but makes NO API call. Confirm the SDK import is acceptable in
  the default suite (Phase-1 `test_coordinator_config.py` already imports SDK types in the default
  suite — precedent exists). If you prefer strict separation, mark it `integration`; recommended:
  keep it default (no network) to gate the parsing logic cheaply. Construct `AssistantMessage`/
  `ToolUseBlock` with the exact fields the installed version requires (check `types.py` — e.g.
  `ToolUseBlock(id=..., name=..., input=...)`, `AssistantMessage(content=[...], model=...)`).
- **VALIDATE:** `../../.venv/bin/pytest tests/test_loop_task_parsing.py -q` → all pass, no network.

### Task 13 — CREATE `tests/test_phase2_parallel_live.py`: fan-out + fallback (integration)

- **IMPLEMENT:** mirror `test_phase1_spine_live.py` header (imports, `_runnable`, `pytestmark`).
  Add fixtures/usage via `conftest.py` (extend it with a `run_parallel` and `run_single_agent`
  fixture if convenient, or call the builders directly through `run_turn`).
  - `test_broad_query_fans_out_in_parallel`: run the parallel coordinator on a 3-subtopic question.
    Assert: `run.max_parallel_delegations >= 2` (delegations emitted in ONE turn — the parallelism
    proof), `run.delegated_subagents & {"web_search","doc_analysis"}` non-empty and ⊆ the two,
    `run.subtype == "success"`, `run.terminated_by_cap is False`, `run.final_text` non-empty with a
    citation bracket AND a corpus year (guards the "launched agents" false-finish), ≥2 facet
    keywords present (lenient breadth signal).
  - `test_simple_query_uses_single_agent_fallback`: `run = await run_research("What year was Stable
    Diffusion released?")`. Assert: `run.route == triage.ROUTE_SINGLE_AGENT`, `run.delegations ==
    []`, `"Agent" not in run.tool_calls`, `"web_search" in run.tool_calls` (it answered directly),
    `run.subtype == "success"`. This is the TR3/TR10 acceptance demo.
- **PATTERN:** `tests/test_phase1_spine_live.py:19-85` (marker gate, structural assertions,
  citation guard).
- **IMPORTS:** `import config, triage`; `import pytest`; run harness via `conftest` fixtures.
- **GOTCHA:** live/costly — gated behind `-m integration` and skipped without CLI/API. If the
  spike chose Path B, the parallelism assertion still holds (`delegation_batches` records the
  single-message batch regardless of foreground/background). Keep subagent-facing text benign.
- **VALIDATE:** `../../.venv/bin/pytest -m integration tests/test_phase2_parallel_live.py -q`
  (requires credentials) → passes.

### Task 14 — UPDATE `tests/test_coordinator_config.py`: cover new builders (unit)

- **IMPLEMENT:** add cases:
  - `build_single_agent_options()`: `tools == []`, `"Agent" not in (allowed_tools or [])`,
    `not agents`, `model == config.WORKER_MODEL`, `_WEB_SEARCH_TOOL in allowed_tools`.
  - `build_sequential_coordinator_options()`: has `"Agent"`, both subagents, and its
    `system_prompt != build_coordinator_options().system_prompt` (distinct baseline).
  - subagents carry the spike-decided `background` value (assert on `web_search_agent.background`).
- **PATTERN:** `tests/test_coordinator_config.py:15-43`.
- **IMPORTS:** extend existing imports with the new builders.
- **VALIDATE:** `../../.venv/bin/pytest tests/test_coordinator_config.py -q` → all pass.

### Task 15 — UPDATE `_tasks/todo.md` and memory; run full suites

- **IMPLEMENT:** append a Phase-2 checklist + review section to `_tasks/todo.md` (mirror the
  Phase-1 structure: scope guardrails, steps, validation checkboxes, review). Update memory
  `mar-agent-sdk-delegation` with the confirmed parallel recipe (Path A/B, `background` value,
  whether results returned inline). Run both suites.
- **VALIDATE:** `../../.venv/bin/pytest -q` (units green, fast) then `../../.venv/bin/pytest -m
  integration -q` (live green). Then `../../.venv/bin/python benchmark_parallel.py` and record the
  speedup in the review.

---

## TESTING STRATEGY

### Unit Tests (default `pytest`, deterministic, free)

- `test_triage.py` — labeled query table; canonical broad → `fan_out`, canonical lookups →
  `single_agent`, ambiguous → default `fan_out`. Fixtures/assertions follow the sibling's
  boundary-table style (`test_hooks_refund_gate.py`).
- `test_loop_task_parsing.py` — synthetic messages through `_ingest_message`: multi-block
  assistant message → `delegation_batches`/`max_parallel_delegations`; `TaskNotificationMessage`
  → `task_events` + `subagent_total_tokens`; `TaskUpdatedMessage` terminal handling;
  subagent-internal message ignored (TR6). No network.
- `test_coordinator_config.py` (extended) — the three builders' option shapes + subagent
  `background`.

### Integration Tests (`pytest -m integration`, live)

- `test_phase2_parallel_live.py` — broad query fans out in parallel (`max_parallel_delegations >=
  2`, clean synthesis with citations); simple query takes the single-agent fallback
  (`route == single_agent`, no `Agent`, `web_search` used).
- Re-run `test_phase1_spine_live.py` — must still pass under the promoted parallel coordinator
  (regression gate: the parallel prompt must not break the ≥2-delegation / both-subagents /
  citation contract).

### Edge Cases

- **Coordinator ends turn early** ("launched agents, will report back") — caught by the
  citation-bracket + corpus-year assertion on `final_text`; the spike (Task 2) is the primary
  guard, the live test the backstop.
- **A subagent times out / is killed** — Phase 4 territory; here just ensure `task_events`
  records a terminal status via `TaskUpdatedMessage` (unit) without crashing the loop.
- **Ambiguous triage input** — defaults to `fan_out` (safe over-coverage), asserted in the unit
  table.
- **`TaskUsage` absent** on a notification (`usage=None`) — loop extracts defensively; asserted by
  a synthetic case with `usage=None`.
- **Single delegation only** (`max_parallel_delegations == 1`) — not parallel; the broad-query
  test requires ≥2 so a coordinator that regressed to sequential fails loudly.

---

## VALIDATION COMMANDS

Run from the project root `projects/multi-agent-research-agent/`. Python is the shared venv:
`../../.venv/bin/python` (there is no project-local venv).

### Level 1: Syntax & Import Sanity

```
../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import triage, loop, config, coordinator; print('imports ok')"
```

### Level 2: Unit Tests (deterministic, free)

```
../../.venv/bin/python -m pytest -q            # full default suite; Phase-1's 22 + new units, ~1-2s
../../.venv/bin/python -m pytest tests/test_triage.py tests/test_loop_task_parsing.py tests/test_coordinator_config.py -q
```

### Level 3: Integration Tests (live, requires `claude` CLI or ANTHROPIC_API_KEY)

```
../../.venv/bin/python -m pytest -m integration -q
```

### Level 4: Manual Validation

```
../../.venv/bin/python run_example.py          # broad Q → ROUTE: fan_out, MAX PARALLEL DELEGATIONS >= 2, cost line
../../.venv/bin/python benchmark_parallel.py    # prints sequential vs parallel wall-clock + speedup > 1.0
```

### Level 5: Additional Validation (optional)

- `git diff --stat` to confirm only the intended files changed; `git grep -n "background=" src/agents`
  to confirm the spike-decided value is set on both subagents.

---

## ACCEPTANCE CRITERIA

- [ ] **Parallel fan-out demonstrated:** a broad 3-subtopic query yields `run.max_parallel_delegations
      >= 2` (all `Agent` calls in ONE coordinator message) and still synthesizes a cited briefing
      (TR2/FR3).
- [ ] **Measurably faster than sequential:** `benchmark_parallel.py` reports parallel wall-clock <
      sequential (speedup > 1.0) on the 3-subtopic query; the number is recorded in `_tasks/todo.md`.
- [ ] **Dynamic selection works:** a narrow lookup routes to `single_agent` — `run.route ==
      ROUTE_SINGLE_AGENT`, `run.delegations == []`, no `Agent` tool call, but `web_search` was used
      to answer directly (TR3/TR10).
- [ ] **Triage is deterministic:** `test_triage.py` passes; same input → same route; canonical
      broad and lookup queries classify correctly.
- [ ] **Instrumentation correct:** `test_loop_task_parsing.py` passes — delegation batches, Task
      events, per-subagent tokens, and TR6 isolation all verified on synthetic messages, no network.
- [ ] **No regressions:** the full default suite passes fast; `test_phase1_spine_live.py` still
      passes under the promoted parallel coordinator; `test_coordinator_config.py` green.
- [ ] **Cost visibility (TR10):** `run_example.py` prints route + parallelism + token/cost;
      subagent token totals are captured on `AgentRun`.
- [ ] Code follows project conventions (snake_case, flat imports, TR-tagged module docstrings,
      structure-only assertions).

---

## COMPLETION CHECKLIST

- [ ] Task 1 (loop instrumentation) done and unit-covered by Task 12.
- [ ] Task 2 spike run ONCE; Path A/B decided and recorded in `coordinator.py` + memory.
- [ ] Tasks 3–8 (agents `background`, triage, config, parallel prompt, sequential baseline,
      single-agent builder, routing) done, each validated.
- [ ] Tasks 9–10 (run_example, benchmark script) produce correct output.
- [ ] Tasks 11–14 (all tests) green: units in the default suite, live under `-m integration`.
- [ ] Full test suite passes (unit + integration); benchmark speedup recorded.
- [ ] `_tasks/todo.md` Phase-2 review appended; memory updated.
- [ ] No linting/type errors; `git diff` reviewed for scope.

---

## NOTES

**Confirmed design decisions (from the planning conversation):**
- **TR3 dynamic selection = deterministic triage** (not a Haiku LLM classifier). Rationale:
  100% unit-testable without API, matches the sibling's code-backed classification and the
  project's "ground truth is structure" ethos. The Haiku tier is defined in config now
  (`CLASSIFIER_MODEL`) purely as the seam for a future LLM classifier — deferred, not built.
- **Parallelism proof = structural assertion + benchmark script** (not a permanent live A/B
  timing test). Rationale: `max_parallel_delegations >= 2` is a deterministic, non-flaky CI signal
  that the fan-out happened in one turn; the wall-clock number comes from an on-demand script so a
  slow-API day can't red the suite.

**The linchpin risk and why the spike is non-negotiable:** the SDK/CLI may run parallel subagents
in the background by default, causing the coordinator to end its turn without synthesizing. Task 2
pins the actual runtime behavior on the installed version BEFORE the coordinator is finalized —
directly mirroring the Phase-1 Task-0 spike that de-risked delegation. Two committed paths (A:
inline via `background=False`; B: background via Task messages) are both instrumented by the loop,
so the code works regardless of which the spike confirms — only the `background` value and a bit of
prompt steering differ.

**Deliberate Phase-2 scope boundaries (NOT in this phase):**
- Scope partitioning + coverage verification + the refinement loop → **Phase 3** (TR4/TR5). Phase 2
  fans out and routes; it does not yet *verify* that all facets were covered or re-delegate for
  gaps. `Report.coverage`/`gaps` stay stubbed.
- Structured error envelopes, timeout/retry behavior, conflict/temporal annotation, coverage
  rendering → **Phase 4** (TR7/TR8/TR9). The corpus timeout marker (D004) stays inert.
- The single-agent fallback answers narrow lookups; it does NOT do provenance-grade multi-source
  synthesis (that's the fan-out path's job).

**Style note:** the user's global instructions prefer camelCase, but this codebase is uniformly
Python `snake_case` — **match the codebase** (the project convention wins for consistency). All new
modules open with a TR-tagged docstring like every existing `src/*.py`.

**Confidence: 8/10 for one-pass success.** The instrumentation, triage, single-agent fallback, and
tests are low-risk and follow established patterns. The one genuine unknown — parallel-execution
runtime behavior — is quarantined into an explicit spike with two pre-designed outcomes, so even
the "bad" outcome (Path B / background) has a committed implementation. The residual risk is only
whether the coordinator reliably synthesizes after parallel launch; the citation-guard test and the
spike together de-risk it, but a stubborn "launched agents" finish could need extra prompt iteration
(hence 8, not 9).
```

