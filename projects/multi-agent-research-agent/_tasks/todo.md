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
