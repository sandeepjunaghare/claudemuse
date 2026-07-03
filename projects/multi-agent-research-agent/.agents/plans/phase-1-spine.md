# Feature: Phase 1 — Multi-Agent Research Spine

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing. Pay special attention to the naming of existing utils, types, and models in the sibling `../customer-support/` project — mirror them. Import from the right files.

> **Source of truth:** `docs/02-multi-agent-research-system.md` (TR1–TR10, FR1–FR5, acceptance criteria) and `docs/02-multi-agent-research-prd.md` §12 Phase 1. Where prose and these diverge, the spec's TRs win.
> **Confirmed product decisions (from pre-plan):** synthesis is **coordinator-owned** (no dedicated synthesis subagent yet); the seeded corpus is built **full/forward-compatible** now; testing is **deterministic-first + a small integration-marked live suite**.

## Feature Description

Build the minimal working hub-and-spoke research system: a **coordinator** (Opus-tier) that decomposes a research question, **delegates** to two subagents — `web_search` and `doc_analysis` (Sonnet-tier) — via the SDK's built-in delegation tool, receives each subagent's **distilled ~1–2k-token summary** (subagents explore in isolated context windows), and then performs a single **coordinator-owned synthesis pass** into a basic cited report. This is the spine that Phases 2–4 extend (parallelism, dynamic selection, refinement, structured errors, provenance).

## User Story

As a **research requester**, I want to ask a broad question and get back a basic sectioned report assembled from specialist subagents, **so that** I have a working, cited briefing produced by a correct coordinator→subagent topology I can then harden.

As a **builder**, I want the coordinator to actually delegate via the `Agent` tool with all context passed explicitly per subagent — and I want the *no-delegation-tool* failure to be demonstrable — **so that** the multi-agent topology (TR1/TR2) is proven, not assumed.

## Problem Statement

There is **no code** in this project yet — only the spec, PRD, and slash commands. Multi-agent orchestration is the highest-value, hardest-to-get-right pattern, and its failure modes (a coordinator that can't delegate, subagents that silently inherit context, transcripts that blow the lead's window) are exactly what must be proven absent. Phase 1 must stand up a correct topology on the Claude Agent SDK before any hardening.

## Solution Statement

Mirror the sibling `customer-support` project's proven Agent-SDK conventions (config + env loading, in-process MCP server via `@tool`/`create_sdk_mcp_server`, `query()` stream drained to a structured `AgentRun`, `integration`-marked live tests). Add the new multi-agent layer the sibling lacks: `AgentDefinition` subagents passed via `ClaudeAgentOptions(agents={...})`, a coordinator whose base tool set is exactly `{Agent}` (delegation-capable, least-privilege), explicit per-subagent context passing, and coordinator-owned synthesis. Seed a forward-compatible corpus. Assert on **structure** (delegation happened, both subagents ran, a sourced report exists), never on prose.

## Feature Metadata

**Feature Type**: New Capability (greenfield spine)
**Estimated Complexity**: Medium (topology + SDK subagent mechanics are the risk; the rest mirrors the sibling)
**Primary Systems Affected**: New `src/` package (coordinator, agents, tools, mocks, schemas), `run_example.py`, `tests/`, `requirements.txt`, `pytest.ini`
**Dependencies**: `claude-agent-sdk` (0.2.110, already in shared venv), `pytest`, `pytest-asyncio`, `python-dotenv`

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING!

All paths relative to `projects/` unless noted. The sibling is the house-style authority.

- `customer-support/src/config.py` (all 64 lines) — **MIRROR.** Constants + workspace-root `.env` loading via `Path(__file__).resolve().parents[3]`, `load_env()` idempotent, `anthropic_key_present()`. Our `config.py` copies this shape; `parents[3]` resolves identically (`.../projects/<proj>/src/config.py` → monorepo root).
- `customer-support/src/agent.py` (lines 10–27, 130–149) — `ClaudeAgentOptions` construction, `ALLOWED_TOOLS` as fully-qualified `mcp__<server>__<tool>` names, the `tools=[]` / `strict_mcp_config=True` / `max_turns` pattern. **Note the divergence** in this plan: our coordinator uses `tools=["Agent"]`, NOT `tools=[]`.
- `customer-support/src/loop.py` (all 115 lines) — **MIRROR + EXTEND.** `AgentRun` dataclass, `_bare_tool_name`, `_ingest_message`, `run_turn`, the **drain-to-ResultMessage (no early break)** pattern and `terminated_by_cap`. We extend `AgentRun` to record delegations.
- `customer-support/src/tools/server.py` (lines 1–93, i.e. the header, `_text`, `_result`, and `get_customer`) — **MIRROR.** `create_sdk_mcp_server` + `@tool(name, rich_description, json_schema)`, the `_result(text, structured, is_error)` envelope, rich disambiguating descriptions.
- `customer-support/src/errors.py` (all 68 lines) — **READ; CRITICAL GOTCHA.** Documents (confirmed in SDK source `claude_agent_sdk/_internal/query.py:644-695`) that **`structuredContent` is dropped before the model or any hook sees it** — only `content` *text* reaches the model. Our `web_search` tool must therefore encode source/date/excerpt **in the text**, not only in `structuredContent`. (Phase 1 uses no error envelope yet; Phase 4 will mirror this file.)
- `customer-support/src/mocks/fixtures.py` (lines 1–70) — **MIRROR style.** SDK-free seed data module (dicts keyed by id) + pure accessors, unit-testable in isolation; comments flag which fields are "staged setup" for later phases. Our `corpus.py` follows this exactly.
- `customer-support/tests/conftest.py` (all 115 lines) — **MIRROR.** `sys.path.insert(0, str(_SRC))` so tests use flat absolute imports (`import config`, `from loop import run_turn`); `agent_runnable()` = `shutil.which("claude") is not None or config.anthropic_key_present()`; lazy SDK import inside fixtures so the deterministic suite never imports the SDK at collection time.
- `customer-support/tests/test_phase1_order_status.py` (all 80 lines) — **MIRROR.** `pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _runnable, ...)]`; assertions on `run.tool_calls` membership/order + `run.subtype == "success"` + `run.terminated_by_result` / `terminated_by_cap`; one lenient substring check as a resolution signal, never a phrasing assertion.
- `customer-support/run_example.py` (all 31 lines) — **MIRROR.** `sys.path.insert(0, "src")`, `config.load_env()`, `asyncio.run(main())`, print `tool_calls` / `subtype` / final text.
- `customer-support/pytest.ini` — **MIRROR verbatim** (`asyncio_mode = auto`, `testpaths = tests`, `integration` marker).
- `customer-support/requirements.txt` — **MIRROR verbatim.**
- `CLAUDE.md` (project) and `docs/02-multi-agent-research-prd.md` §6 (directory structure), §7 (subagents/tools/corpus tables) — the intended architecture.

### New Files to Create

```
requirements.txt                 # claude-agent-sdk, pytest, pytest-asyncio, python-dotenv
pytest.ini                       # mirror sibling
run_example.py                   # single-question end-to-end entry point
src/__init__.py
src/config.py                    # model tiers, MCP server name, backstop, env loading
src/schemas.py                   # SourceRef, Claim, SubagentResult, Report (forward-compatible)
src/loop.py                      # AgentRun (+ delegations) + run_turn, mirrored & extended from sibling
src/coordinator.py               # build_coordinator_options(), build_no_delegation_options(), run_research()
src/agents/__init__.py
src/agents/web_search.py         # AgentDefinition (Sonnet, mcpServers=["research"], web_search tool)
src/agents/doc_analysis.py       # AgentDefinition (Sonnet, web_search tool for fetch-by-ref)
src/tools/__init__.py
src/tools/server.py              # create_sdk_mcp_server + @tool("web_search", ...) over the corpus
src/mocks/__init__.py
src/mocks/corpus.py              # seeded corpus (4+ facets, conflict pair, dated source, timeout marker) + search()
tests/__init__.py
tests/conftest.py                # mirror sibling: sys.path, load_env, agent_runnable(), run_research fixture
tests/test_config.py             # unit
tests/test_schemas.py            # unit
tests/test_corpus.py             # unit
tests/test_tools_web_search.py   # unit
tests/test_coordinator_config.py # unit (the "Agent" allowlist / tools-set assertions)
tests/test_phase1_spine_live.py  # integration (delegation fires, both subagents, report; + negative no-delegate)
```

### Relevant Documentation — READ BEFORE IMPLEMENTING

- Agent SDK — Subagents: https://code.claude.com/docs/en/agent-sdk/subagents
  - `AgentDefinition` fields; how the main agent delegates via the `Agent` tool; per-subagent `tools`/`model`/`mcpServers`.
  - Why: the entire delegation mechanism. **Note the rename:** the delegation tool is `"Agent"` (renamed from `"Task"` in Claude Code v2.1.63). Current SDKs emit `"Agent"` in `tool_use` blocks; `"Task"` may still appear in `system:init` tool lists / `permission_denials`. **Detect both** in the stream.
- Agent SDK — Sessions: https://code.claude.com/docs/en/agent-sdk/sessions
  - Subagent transcript isolation; `list_subagents`/`get_subagent_messages` are file/store-backed (under `<sessionId>/subagents/agent-<id>.jsonl`), **not** stream events.
  - Why: confirms Phase 1 fan-out assertions come from the `Agent` tool-use blocks in the stream, not from hooks/helpers.
- Anthropic — "How we built our multi-agent research system" and "Effective context engineering for AI agents" (linked in the spec, §Read first)
  - Why: the coverage/isolation/cost thesis behind TR6/TR10.

### SDK facts verified in installed source (0.2.110) — treat as ground truth

- `AgentDefinition(description, prompt, tools=None, disallowedTools=None, model=None, skills=None, memory=None, mcpServers=None, initialPrompt=None, maxTurns=None, background=None, effort=None, permissionMode=None)`. `model` accepts an alias (`"sonnet"`) or full id (`"claude-sonnet-4-6"`).
- `ClaudeAgentOptions` has `agents: dict[str, AgentDefinition]`, `tools`, `allowed_tools`, `disallowed_tools`, `model`, `mcp_servers`, `strict_mcp_config`, `max_turns`, `hooks`, … (full list confirmed).
- CLI-flag mapping (`_internal/transport/subprocess_cli.py`):
  - `tools=[]` → `--tools ""` (**empty base built-in set**); `tools=["Agent"]` → `--tools Agent`; `tools=None` → no flag (CLI default full built-in set).
  - `allowed_tools` → `--allowedTools` (auto-approve list; does **not** add tools absent from the base set).
  - `agents` → sent via the **initialize control request** (`request["agents"]=...`), no CLI flag.
  - `model` → `--model` (this sets the **coordinator/main** model; sibling proves `options.model="claude-opus-4-8"` works).

### Patterns to Follow (from the sibling)

**Env loading (config.py):**
```python
_WORKSPACE_ENV = Path(__file__).resolve().parents[3] / ".env"   # src/config.py -> monorepo root
def load_env() -> None:
    global _loaded
    if _loaded: return
    load_dotenv(dotenv_path=_WORKSPACE_ENV); _loaded = True
```

**MCP tool + envelope (tools/server.py):**
```python
from claude_agent_sdk import create_sdk_mcp_server, tool
def _result(text, structured, is_error=False):
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured, "is_error": is_error}
@tool("web_search", "<rich description: purpose, inputs, when-to-use>", {"type":"object","properties":{...},"required":[...]})
async def web_search(args): ...
research_server = create_sdk_mcp_server(name="research", tools=[web_search])
```

**Stream drain to AgentRun (loop.py) — keep the no-early-break contract:**
```python
async for message in query(prompt=prompt, options=options):
    rt = _ingest_message(message, run, text_parts)
    if rt is not None: result_text = rt
```

**Live-test skip guard (tests):**
```python
_runnable = shutil.which("claude") is not None or config.anthropic_key_present()
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _runnable, reason="...")]
```

**Naming:** Python `snake_case` for functions/vars, `PascalCase` for classes/dataclasses (per global style). Tool names bare (`web_search`); fully-qualified tool ids `mcp__research__web_search`.

---

## IMPLEMENTATION PLAN

### Phase A: Foundation
Scaffold deps + config + forward-compatible schemas + the seeded corpus. All SDK-free and unit-testable.

**Tasks:** requirements/pytest.ini; `config.py` (model tiers, server name, backstop, env); `schemas.py` (SourceRef/Claim/SubagentResult/Report); `mocks/corpus.py` (seed data + `search()`).

### Phase B: Core Implementation
The MCP tool + the two subagents + the coordinator + the run driver.

**Tasks:** `tools/server.py` (`web_search`); `agents/web_search.py` + `agents/doc_analysis.py` (`AgentDefinition`s); `loop.py` (AgentRun + delegation capture); `coordinator.py` (working + no-delegation options, `run_research`).

### Phase C: Integration
Wire the entry point; confirm delegation actually fires end-to-end (the Step-0 empirical check lives here — it gates correctness).

**Tasks:** `run_example.py`; run a live smoke to confirm an `Agent` tool-use block appears and subagent results come back inline (not stranded in background).

### Phase D: Testing & Validation
Deterministic unit suite (default) + integration-marked live suite (delegation, both subagents, report, and the negative no-delegate demo).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each is atomic and independently testable.

### Task 0 — SPIKE: empirically confirm the delegation-tool config (do this FIRST)
- **IMPLEMENT**: Before writing `coordinator.py`, run a throwaway `query()` with a trivial coordinator (`tools=["Agent"]`, one dummy `AgentDefinition`, `mcp_servers={"research": ...}`, a prompt that forces one delegation) and print every `block.name` seen. Confirm: (1) a tool-use block with `name in ("Agent","Task")` appears; (2) its `input` contains `subagent_type` + `prompt`; (3) the subagent's result returns **inline** (a `ToolResultBlock`) so the coordinator can synthesize — i.e. it did not run detached in the background. Then confirm `tools=[]` yields **no** such block.
- **PATTERN**: `customer-support/src/loop.py:71-89` (block iteration).
- **GOTCHA**: Recent CLIs default subagents to background (`run_in_background`). If results don't come back inline, add an explicit instruction to the coordinator system prompt ("wait for each subagent's results before synthesizing; do not run them detached") and/or set `AgentDefinition(background=False)`. Verify which is needed here.
- **VALIDATE**: `../../.venv/bin/python scratchpad_spike.py` prints an `Agent`/`Task` block for the working config and none for `tools=[]`. Delete the spike after. (Put it in the scratchpad dir, not the repo.)

### Task 1 — CREATE requirements.txt + pytest.ini + install
- **IMPLEMENT**: `requirements.txt` = `claude-agent-sdk`, `pytest`, `pytest-asyncio`, `python-dotenv` (one per line). `pytest.ini` = mirror sibling verbatim.
- **PATTERN**: `customer-support/requirements.txt`, `customer-support/pytest.ini`.
- **IMPORTS**: n/a.
- **GOTCHA**: Install into the **shared** venv; this project has none of its own.
- **VALIDATE**: `../../.venv/bin/pip install -r requirements.txt && ../../.venv/bin/python -c "import claude_agent_sdk, pytest, dotenv; print('ok')"`

### Task 2 — CREATE src/__init__.py + src/config.py
- **IMPLEMENT**: `COORDINATOR_MODEL = "claude-opus-4-8"`, `WORKER_MODEL = "claude-sonnet-4-6"`, `MCP_SERVER_NAME = "research"`, `MAX_TURNS_BACKSTOP = 20`, `MAX_REFINEMENT_ITERATIONS = 2` (defined now, unused until Phase 3), `load_env()`, `anthropic_key_present()`. `_WORKSPACE_ENV = Path(__file__).resolve().parents[3] / ".env"`.
- **PATTERN**: `customer-support/src/config.py:1-63` (near-verbatim).
- **GOTCHA**: `parents[3]` from `src/config.py`, not `parents[2]`. Verify the path resolves to the monorepo root that holds `.env`.
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "import config; config.load_env(); print(config.COORDINATOR_MODEL, config._WORKSPACE_ENV.exists())"`

### Task 3 — CREATE src/schemas.py
- **IMPLEMENT**: `@dataclass` `SourceRef(name: str, url: str | None, excerpt: str, date: str)`; `Claim(text: str, source: SourceRef)`; `SubagentResult(facet: str, summary: str, claims: list[Claim], status: str = "ok")`; `Report(sections: list[dict], claims: list[Claim], coverage: dict[str, str] = field(default_factory=dict), gaps: list[str] = field(default_factory=list))`. Content separated from metadata so Phases 3–4 add coverage/gaps/conflict without reshaping. Add a `Report.all_claims_have_source() -> bool` helper (used by the 100%-citation test later).
- **PATTERN**: dataclass style per global conventions; mirror the "staged for later phases" comment style of `fixtures.py`.
- **IMPORTS**: `from dataclasses import dataclass, field`.
- **GOTCHA**: Keep `date` a plain ISO string (the corpus stores heterogeneous dates as data; no parsing in Phase 1).
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "import schemas; r=schemas.Report([], []); print(r.coverage, r.all_claims_have_source())"`

### Task 4 — CREATE src/mocks/__init__.py + src/mocks/corpus.py (full, forward-compatible)
- **IMPLEMENT**: Topic **"impact of AI on creative industries"**. `DOCUMENTS: list[dict]`, each `{id, facet, source, date, url, content}`. Cover **4+ facets**: `visual_art`, `music`, `writing`, `film`. Include:
  - **(b) conflict pair:** two credible docs giving *different values* for one figure (e.g. "share of studios using AI tools": SourceA 40% dated 2023, SourceB 55% dated 2025) — same facet, both credible.
  - **(c) differently-dated source:** ensure the conflict pair (or another pair) carries clearly different `date`s so temporal handling (Phase 4) is exercisable.
  - **(d) timeout marker:** one doc/endpoint flagged `{"timeout": True}` (marker only — the tool ignores it in Phase 1; Phase 4 turns it into a structured timeout error).
  - `FACETS = ["visual_art", "music", "writing", "film"]` exported for coverage tests.
  - `search(query: str, facet: str | None = None) -> list[dict]`: simple case-insensitive substring/keyword match over `content`+`facet`, optionally filtered by `facet`. Never raises.
- **PATTERN**: `customer-support/src/mocks/fixtures.py:1-37` (SDK-free seed dicts + pure accessors + "staged for later phase" comments).
- **GOTCHA**: SDK-free (no imports from the SDK) so it unit-tests without credentials. Do **not** implement timeout/error behavior here — that's Phase 4; the marker is inert data now.
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "import mocks.corpus as c; print(sorted(c.FACETS)); print(len(c.search('AI', facet='music')))"`

### Task 5 — CREATE src/tools/__init__.py + src/tools/server.py
- **IMPLEMENT**: `@tool("web_search", <rich description>, <json schema {query: str, facet?: str}>)` async fn that calls `mocks.corpus.search(...)` and returns `_result(text, structured, is_error=False)`. **Encode each hit's source name, date, and a short excerpt in the `text`** (one line per hit, e.g. `"[<source>, <date>] <excerpt> (facet: <facet>)"`) because `structuredContent` never reaches the model. Also populate `structuredContent={"results":[...]}` for contract fidelity. Rich description states purpose, the `query`/`facet` inputs with examples, and when to use it. Build `research_server = create_sdk_mcp_server(name=config.MCP_SERVER_NAME, tools=[web_search])`.
- **PATTERN**: `customer-support/src/tools/server.py:26-93` (`_text`/`_result`, `@tool`, rich description).
- **IMPORTS**: `from claude_agent_sdk import create_sdk_mcp_server, tool`; `import config`; `from mocks import corpus`.
- **GOTCHA**: The fully-qualified tool id is `f"mcp__{config.MCP_SERVER_NAME}__web_search"` = `mcp__research__web_search` — used in `allowed_tools` and each subagent's `tools`. Phase 1 returns `is_error=False` always (no timeout handling yet).
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "from tools.server import web_search, research_server; print(research_server.name if hasattr(research_server,'name') else 'server ok')"`

### Task 6 — CREATE src/agents/__init__.py + src/agents/web_search.py
- **IMPLEMENT**: `web_search_agent = AgentDefinition(description=..., prompt=<output contract>, model=config.WORKER_MODEL, tools=[f"mcp__{config.MCP_SERVER_NAME}__web_search"], mcpServers=[config.MCP_SERVER_NAME])`. Prompt states: you receive a subtopic + source-type scope + query hints **in this message** (you inherit nothing); use `web_search` to gather sources for your assigned facet only; return a **distilled ~1–2k-token summary** plus a structured list of `claim → source → date` lines (one per line) drawn from the tool's text; do not dump raw search output (TR6).
- **PATTERN**: PRD §7.1 table (web_search row); AgentDefinition signature above.
- **IMPORTS**: `from claude_agent_sdk import AgentDefinition`; `import config`.
- **GOTCHA**: `mcpServers` references the in-process server **by name string** (`"research"`), matching the coordinator's `mcp_servers` key. The subagent inherits neither tools nor context — both must be declared/passed explicitly.
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "from agents.web_search import web_search_agent; print(web_search_agent.model, web_search_agent.tools)"`

### Task 7 — CREATE src/agents/doc_analysis.py
- **IMPLEMENT**: `doc_analysis_agent = AgentDefinition(description=..., prompt=<output contract>, model=config.WORKER_MODEL, tools=[f"mcp__{config.MCP_SERVER_NAME}__web_search"], mcpServers=[config.MCP_SERVER_NAME])`. Prompt: you receive a document reference (id/source) + an extraction goal **in this message**; fetch it via `web_search` (query its id/source) and extract structured claims with excerpts + dates; return a distilled summary + `claim → source → date` lines.
- **PATTERN**: PRD §7.1 (doc_analysis row).
- **GOTCHA**: Phase-1 simplification — `doc_analysis` reuses the `web_search` tool to fetch by reference (no separate fetch tool). Note this for Phase 4 revisit. Still must receive its target **explicitly** in the prompt (TR2).
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "from agents.doc_analysis import doc_analysis_agent; print(doc_analysis_agent.model)"`

### Task 8 — CREATE src/loop.py (MIRROR + EXTEND sibling)
- **IMPLEMENT**: Copy `AgentRun`, `_bare_tool_name`, `_ingest_message`, `run_turn` from the sibling. **Extend** `AgentRun` with `delegations: list[dict]` (each `{"subagent_type": ..., "prompt_excerpt": ...}`) and a `delegated_subagents` property (set of `subagent_type`s). In `_ingest_message`, when a `ToolUseBlock` has `block.name in ("Agent", "Task")`, append to `delegations` using `block.input.get("subagent_type")` and a truncated `prompt`. Keep the **drain-to-ResultMessage / no early break** contract and `terminated_by_cap`.
- **PATTERN**: `customer-support/src/loop.py` (all of it) — this is a near-copy plus the delegation capture.
- **IMPORTS**: `from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query`.
- **GOTCHA**: Match **both** `"Agent"` and `"Task"` (rename compat). Do not break on the `ResultMessage`; the async generator tears down badly on early `break` (documented in the sibling).
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "import loop; r=loop.AgentRun(); print(r.delegations, r.terminated_by_cap)"`

### Task 9 — CREATE src/coordinator.py
- **IMPLEMENT**:
  - `SYSTEM_PROMPT` (coordinator): decompose the question into a few distinct subtopics/facets; **delegate** retrieval to `web_search` and document extraction to `doc_analysis` using the delegation tool, passing **all** needed context explicitly in each subagent's prompt (they inherit nothing); **wait for each subagent's results**; then **synthesize one basic report yourself** — sections per facet, every claim carrying its source + date exactly as the subagents reported them; do not invent facts or drop sources. (Phase-1 scope: sequential delegation is fine; parallelism is Phase 2.)
  - `build_coordinator_options() -> ClaudeAgentOptions` with `model=config.COORDINATOR_MODEL`, `system_prompt=SYSTEM_PROMPT`, `tools=["Agent"]`, `mcp_servers={config.MCP_SERVER_NAME: research_server}`, `allowed_tools=["Agent", f"mcp__{config.MCP_SERVER_NAME}__web_search"]`, `agents={"web_search": web_search_agent, "doc_analysis": doc_analysis_agent}`, `strict_mcp_config=True`, `max_turns=config.MAX_TURNS_BACKSTOP`.
  - `build_no_delegation_options() -> ClaudeAgentOptions`: identical but `tools=[]` and `agents={}` (or `allowed_tools` omitting `"Agent"`) — the coordinator that **cannot delegate** (acceptance demo).
  - `async def run_research(question: str) -> AgentRun`: `return await run_turn(question, build_coordinator_options())`.
- **PATTERN**: `customer-support/src/agent.py:130-149` (options construction) — but `tools=["Agent"]`, not `tools=[]`.
- **IMPORTS**: `from claude_agent_sdk import ClaudeAgentOptions`; `import config`; `from tools.server import research_server`; `from agents.web_search import web_search_agent`; `from agents.doc_analysis import doc_analysis_agent`; `from loop import run_turn, AgentRun`.
- **GOTCHA**: `tools=["Agent"]` is the linchpin (Task 0). `tools=[]` strips the delegation tool → no fan-out (that IS the negative config). Whether the coordinator needs an explicit "wait, don't background" instruction depends on Task 0's finding — apply it here.
- **VALIDATE**: `cd src && ../../../.venv/bin/python -c "from coordinator import build_coordinator_options, build_no_delegation_options; o=build_coordinator_options(); print('Agent' in o.allowed_tools, list(o.agents.keys())); n=build_no_delegation_options(); print('Agent' in (n.allowed_tools or []))"`

### Task 10 — CREATE run_example.py
- **IMPLEMENT**: `sys.path.insert(0, "src")`, `config.load_env()`, `run = asyncio.run(run_research("What is the impact of AI on creative industries?"))`, print `run.delegated_subagents`, `run.subtype`, and `run.final_text`. Also print a token/turn line (`run.num_turns`) as TR10 groundwork.
- **PATTERN**: `customer-support/run_example.py` (verbatim structure).
- **VALIDATE**: `../../.venv/bin/python run_example.py` prints a report mentioning multiple facets with bracketed sources (needs credentials; this is the manual Level-4 check).

### Task 11 — CREATE tests/__init__.py + tests/conftest.py
- **IMPLEMENT**: Mirror sibling conftest: `sys.path.insert(0, str(_SRC))`; `import config; config.load_env()`; `agent_runnable()`; a `run_research` fixture that **lazy-imports** `coordinator.run_research` (so `-m "not integration"` never imports the SDK).
- **PATTERN**: `customer-support/tests/conftest.py:1-98`.
- **GOTCHA**: Keep SDK imports lazy/inside fixtures; corpus/schemas/config import eagerly (SDK-free).
- **VALIDATE**: `../../.venv/bin/python -m pytest -q --collect-only` collects with no import errors.

### Task 12 — CREATE unit tests (deterministic, no credentials)
- **IMPLEMENT**:
  - `test_config.py`: `COORDINATOR_MODEL` is Opus id, `WORKER_MODEL` is Sonnet id, `_WORKSPACE_ENV` exists.
  - `test_schemas.py`: construct a `Report` with claims; `all_claims_have_source()` true when every claim has a `SourceRef`, false if one is `None`.
  - `test_corpus.py`: `len(FACETS) >= 4`; the conflict pair exists (two docs, same facet, different values, different dates); a `timeout`-marked doc exists; `search("AI", facet="music")` returns only music docs.
  - `test_tools_web_search.py`: calling the tool fn returns `is_error=False` and the **content text** contains a source name + date for a matched query (asserts the "encode in text" contract).
  - `test_coordinator_config.py`: `"Agent" in build_coordinator_options().allowed_tools`; `build_coordinator_options().tools == ["Agent"]`; both subagents present in `.agents`; each subagent `.model == WORKER_MODEL` and lists the `mcp__research__web_search` tool; `build_no_delegation_options()` has `tools == []` and no `"Agent"` in `allowed_tools`.
- **PATTERN**: assertion style from `customer-support/tests/test_fixtures.py` / `test_tools_errors.py` (structure, not prose).
- **IMPORTS**: call the tool coroutine via `asyncio.run(...)` or rely on `asyncio_mode=auto` with `async def` tests.
- **VALIDATE**: `../../.venv/bin/python -m pytest -m "not integration" -q` → all green, no SDK import, fast.

### Task 13 — CREATE tests/test_phase1_spine_live.py (integration)
- **IMPLEMENT**: `pytestmark = [pytest.mark.integration, pytest.mark.skipif(not agent_runnable(), ...)]`.
  - `test_coordinator_delegates_to_both_subagents`: `run = await run_research("impact of AI on creative industries")`; assert `len(run.delegations) >= 2`; assert `{"web_search","doc_analysis"} <= run.delegated_subagents`; assert `run.terminated_by_result and not run.terminated_by_cap`; assert `run.final_text` is non-empty and mentions ≥2 facet keywords (lenient).
  - `test_report_claims_carry_sources` (lenient Phase-1 signal): assert the report text contains bracketed source/date markers (e.g. a `[`…`]` citation) — full 100%-citation structural assertion lands in Phase 4.
  - `test_no_delegation_config_cannot_delegate` (**negative / acceptance demo**): `run = await run_turn("impact of AI on creative industries", build_no_delegation_options())`; assert **no** delegation occurred (`run.delegations == []` and neither `"Agent"` nor `"Task"` in `run.tool_calls`). The coordinator may still answer from its own knowledge — that's fine; the point is it could not fan out.
- **PATTERN**: `customer-support/tests/test_phase1_order_status.py` (marker, skip guard, structural assertions, lenient substring).
- **GOTCHA**: These cost real API calls (~1 Opus + 2 Sonnet each). They only run under `-m integration`.
- **VALIDATE**: `../../.venv/bin/python -m pytest -m integration -q` → green with credentials.

---

## TESTING STRATEGY

### Unit Tests (default `pytest`, deterministic, free)
`config`, `schemas`, `corpus`, `web_search` tool return shape, and **coordinator options construction** (the `"Agent"` allowlist / `tools=["Agent"]` vs `tools=[]` assertions). No SDK import at collection time (lazy imports in fixtures). Ground truth = structure.

### Integration Tests (`pytest -m integration`, live SDK)
Delegation fires to **both** subagents; run terminates on a `ResultMessage` (not the cap); a non-empty, facet-spanning, source-bracketed report is produced; and the **no-delegation config demonstrably cannot fan out**. Assert on `AgentRun` structure (`delegations`, `delegated_subagents`, `subtype`, `terminated_by_cap`), never on wording.

### Edge Cases
- No credentials → integration tests **skip** (not fail) via `agent_runnable()`.
- `tools=[]` coordinator → zero delegations (asserted).
- Subagents backgrounded and not awaited → caught by Task 0; mitigate via system-prompt instruction / `background=False`.
- Corpus `search()` with no match → returns `[]`, tool returns `is_error=False` with an empty-result text (valid empty, not an error — full access-vs-empty distinction is Phase 4).

---

## VALIDATION COMMANDS

Run from the project root: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/multi-agent-research-agent`. Python is `../../.venv/bin/python`.

### Level 1: Syntax & Import
```
../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config, schemas, mocks.corpus, tools.server, agents.web_search, agents.doc_analysis, loop, coordinator; print('imports ok')"
```

### Level 2: Unit Tests
```
../../.venv/bin/python -m pytest -m "not integration" -q
```

### Level 3: Integration Tests (needs `claude` CLI login or ANTHROPIC_API_KEY)
```
../../.venv/bin/python -m pytest -m integration -q
```

### Level 4: Manual Validation
```
../../.venv/bin/python run_example.py
```
Expect: `delegated_subagents` includes `web_search` and `doc_analysis`; `subtype == "success"`; the printed report spans multiple facets with bracketed `[source, date]` citations.

### Level 5: Full Suite
```
../../.venv/bin/python -m pytest -q
```

---

## ACCEPTANCE CRITERIA

- [ ] A coordinator with `tools=["Agent"]` **delegates** to both `web_search` and `doc_analysis` (structurally asserted via `AgentRun.delegated_subagents`).
- [ ] Subagents receive their subtopic/scope **only via their prompt** (no inheritance) — encoded in agent prompts and the coordinator's delegation instruction (TR2).
- [ ] Each subagent returns a **distilled summary** (contract stated in its prompt; not a raw transcript) (TR6).
- [ ] The coordinator produces a **basic report** with per-facet sections and claims carrying `[source, date]` (FR1; full 100%-citation structural check deferred to Phase 4).
- [ ] The **no-delegation config (`tools=[]`) demonstrably cannot delegate** — permanent negative test (acceptance demo).
- [ ] Loop terminates on a `ResultMessage`, **not** the `max_turns` cap (TR1).
- [ ] `pytest -m "not integration"` passes fast with **no SDK import**; `pytest -m integration` passes with credentials.
- [ ] Phase-1 scope respected: **no** parallelism, dynamic selection, refinement, structured errors, or conflict/temporal handling (those are Phases 2–4).

## COMPLETION CHECKLIST

- [ ] Task 0 spike confirmed the working/negative delegation configs and inline-result behavior (spike deleted).
- [ ] All tasks completed in order; each task's VALIDATE command passed.
- [ ] Level 1–5 validation commands all pass (integration with credentials).
- [ ] No linting/style drift from sibling conventions.
- [ ] `_tasks/todo.md` items checked off; a short review section appended.
- [ ] Code reviewed for quality; import paths match the sibling's flat `src/`-on-path convention.

## NOTES

- **Biggest risk (mitigated by Task 0):** the delegation-tool config. The Agent SDK renamed `Task`→`Agent`; `--tools` sets the base built-in set (`tools=["Agent"]` keeps only delegation; `tools=[]` removes it). Detect **both** names in the stream. The prior guidance to use `tools=[]` for the working coordinator was wrong — that's the *negative* config.
- **`structuredContent` is dropped before the model sees it** (SDK source `query.py:644-695`). The `web_search` tool must put source/date/excerpt in the **content text**. This also foreshadows how Phase 4 provenance must flow.
- **Background subagents:** recent CLIs may background subagents by default; the coordinator must obtain results inline to synthesize. Resolve empirically in Task 0; mitigate via system-prompt instruction or `AgentDefinition(background=False)`.
- **Deliberate Phase-1 simplifications:** sequential (not parallel) delegation; `doc_analysis` reuses the `web_search` tool to fetch by reference; corpus timeout/conflict entries are inert data now. All are revisited in later phases and flagged in code comments.
- **Cost awareness:** real tiers during dev (Opus coordinator + Sonnet workers) so decomposition quality isn't masked; each live run ≈ 1 Opus + 2 Sonnet.

---

**Confidence score for one-pass success: 8/10.** High confidence on scaffold/config/schemas/corpus/tests (direct sibling mirror) and on the delegation-config recipe (verified in SDK source). The −2 is live-behavior uncertainty the model controls: whether the coordinator reliably delegates to *both* subagents in one Phase-1 run and awaits results inline vs. backgrounding — Task 0 de-risks this before the real code is written, and the system prompt is the tuning surface if a run under-delegates.
