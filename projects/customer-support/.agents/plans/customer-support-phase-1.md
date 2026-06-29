# Feature: Customer Support Resolution Agent — Phase 1 (Loop + Four MCP Tools)

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing. Pay special attention to the **exact `claude-agent-sdk` API surface of the installed version** (see GOTCHAs) and to importing from the right modules.

## Feature Description

Stand up the foundation of the Customer Support Resolution Agent on the **Claude Agent SDK** (`claude-agent-sdk`): a working agentic loop, the **four** MCP tools (`get_customer`, `lookup_order`, `process_refund`, `escalate_to_human`) with rich, disambiguating descriptions, and a mocked backend with seeded fixtures. The end-to-end success target for this phase is resolving a **simple order-status query**: the agent verifies the customer, looks up the order, and answers — terminating cleanly when done.

This phase deliberately **excludes** the deterministic guardrails (refund PreToolUse hook, prerequisite gate, PostToolUse date normalization → Phase 2), structured errors / escalation calibration / handoff (Phase 3), and context hygiene / multi-issue (Phase 4). All four tools are *created* here, but `process_refund` and `escalate_to_human` carry no hook enforcement yet — the structure is laid so hooks slot in cleanly in later phases.

## User Story

As a **retail customer**
I want to **ask about my order's status in plain language**
So that **I get an accurate answer end-to-end without filling out a form or waiting for a human** — and behind the scenes the agent verifies who I am before looking up my order.

## Problem Statement

There is no implementation yet — only a spec. We need a verifiably-correct agentic loop and a least-privilege tool surface that a real LLM drives reliably: it must pick the **right** tool (not confuse the two deliberately-similar lookup tools), chain identity-verification before order lookup, and stop on natural completion rather than by parsing text or hitting an iteration cap. Everything downstream (guardrails, escalation, context) builds on this skeleton, so getting the loop semantics and tool descriptions right now is load-bearing.

## Solution Statement

Use the Claude Agent SDK's in-process MCP server (`create_sdk_mcp_server` + `@tool`) to define the four tools backed by an in-memory mock. Configure a single agent via `ClaudeAgentOptions` with `allowed_tools` scoped to exactly those four tools (least privilege, TR2/D2.3) and a **behavior-focused** system prompt that guides "verify identity before order/account/financial operations" without coupling a tool to every turn (avoids the over-trigger trap). Drive the loop with `query()`, treating the SDK's `ResultMessage` as the terminal signal (the Agent SDK manages the `stop_reason` loop internally — this satisfies TR1's *intent*: no text-parsing for completion, `max_turns` only as a backstop). Validate with a pytest suite that **asserts on captured tool calls and the result outcome, not on the model's wording**.

## Feature Metadata

**Feature Type**: New Capability (greenfield foundation)
**Estimated Complexity**: Medium
**Primary Systems Affected**: New `src/` package (agent, tools, mocks) + new `tests/` suite
**Dependencies**: `claude-agent-sdk` (PyPI), `pytest`, `python-dotenv`; **likely also** the Claude Code CLI / Node runtime as a subprocess dependency of the Agent SDK (VALIDATE — see GOTCHAs). Workspace `.env` provides `ANTHROPIC_API_KEY`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: READ THESE BEFORE IMPLEMENTING

This is a greenfield project; the "patterns to mirror" live in the spec and the project rules, not in existing code.

- `docs/01-customer-support-resolution-agent.md` — **the source-of-truth spec.** Read TR1 (agentic loop), TR2 (four tools + disambiguation), and the Phase-1 build-step + acceptance criteria in full. Non-negotiable contracts.
- `docs/02-customer-support-prd.md` — expanded PRD; §6 (proposed `src/` layout — *proposal, confirm names*), §7 (tool table with each tool's purpose/edge cases), §10 (error/handoff/case-facts JSON shapes for later phases), §11 (acceptance checklist).
- `CLAUDE.md` (project root) — the deterministic-vs-probabilistic thesis, the agentic-loop anti-patterns ("don't parse assistant text; don't use a max-iteration cap as the *primary* stop"), the system-prompt "avoid always-verify over-trigger" warning, and the "exactly four tools, two deliberately similar, disambiguate by description" rule.
- `/Users/sandeep/.claude/CLAUDE.md` (global) — camelCase vars / PascalCase types, pytest for Python, check for an existing `tests/` dir before creating test files, concise JSDoc-style comments.

### New Files to Create

- `src/__init__.py` — package marker.
- `src/mocks/__init__.py`
- `src/mocks/fixtures.py` — seeded customers (incl. a duplicate-name pair), orders (with **heterogeneous date formats** for later TR5), and a flaky-503 toggle (off in Phase 1). The in-memory backend access functions live here.
- `src/tools/__init__.py`
- `src/tools/server.py` — the four `@tool` functions + `create_sdk_mcp_server(name="support", ...)`. (Single file is fine for four tools; split per-tool only if it grows.)
- `src/agent.py` — builds `ClaudeAgentOptions` (system prompt, `mcp_servers`, `allowed_tools`, `model`, `max_turns`) and the system prompt string.
- `src/loop.py` — `run_turn(prompt, options) -> AgentRun` async helper: drives `query()`, collects tool-use names and the final `ResultMessage`, returns a structured record the tests assert on.
- `src/config.py` — constants (model id, `max_turns` backstop, refund policy limit placeholder for Phase 2) and `.env` loading.
- `tests/__init__.py`
- `tests/conftest.py` — load `../../.env`, shared fixtures, the `run_agent` harness wrapper.
- `tests/test_phase1_order_status.py` — the Phase-1 happy-path + tool-selection + loop-termination assertions.
- `pyproject.toml` **or** `requirements.txt` + `pytest.ini` — declare deps + pytest config (whichever the execution agent confirms fits the shared-venv setup; prefer a minimal `requirements.txt` since the venv is shared at the workspace root).

### Relevant Documentation — READ THESE BEFORE IMPLEMENTING

- [Claude Agent SDK — Python](https://platform.claude.com/docs/en/agent-sdk/python)
  - Section: `query()` vs `ClaudeSDKClient`, message types, `ClaudeAgentOptions`.
  - Why: the loop, options, and message-stream shapes for TR1.
- [Claude Agent SDK — Custom Tools](https://platform.claude.com/docs/en/agent-sdk/custom-tools)
  - Section: `@tool` decorator, `create_sdk_mcp_server`, tool return shape (`content` / `is_error` / `structuredContent`), `mcp__<server>__<tool>` naming.
  - Why: TR2 tool definitions and `allowed_tools` scoping.
- [Claude Agent SDK — MCP](https://platform.claude.com/docs/en/agent-sdk/mcp)
  - Section: wiring an in-process SDK MCP server into `mcp_servers`.
  - Why: registration + naming for `allowed_tools`.
- [Claude Agent SDK — Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks) — *skim only for Phase 1; central to Phase 2.*
- [PyPI: claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) — confirm installed version + its install prerequisites (CLI/Node — see GOTCHA).
- `claude-api` skill (`shared/models.md`) — model IDs. **Use `claude-opus-4-8`.** (The research that seeded this plan suggested stale IDs like `claude-opus-4-1` / `claude-sonnet-4-20250514` — do not use those.)

### Patterns to Follow

**Naming Conventions:** Python `snake_case` for functions/variables/modules, `PascalCase` for classes/dataclasses (per global rules). Tool *names* are `snake_case` matching the spec exactly: `get_customer`, `lookup_order`, `process_refund`, `escalate_to_human`. Fully-qualified tool names for `allowed_tools`: `mcp__support__<tool_name>`.

**Tool return shape (mirror in every tool):**
```python
{
    "content": [{"type": "text", "text": "<human-readable summary>"}],
    "structuredContent": { ... },   # machine-readable; the fields the model reasons over
    "is_error": False,              # True for failures (structured errors are Phase 3)
}
```

**Async everywhere:** `@tool` handlers are `async def`; the loop runs under `asyncio`. Tests use `pytest.mark.asyncio` (add `pytest-asyncio`) or `asyncio.run` in a sync test body.

**Loop termination (TR1 — mirror exactly):** iterate the `query()` async generator; collect `ToolUseBlock` names from `AssistantMessage.content`; finish when a `ResultMessage` arrives and inspect `message.subtype` (`"success"` vs error/`max_turns` variants). **Never** parse assistant text to decide completion. `max_turns` is a *backstop*, asserted to be NOT the terminating reason on the happy path.

**System prompt (behavior, not tool-coupling):** describe *when* to verify identity (before any order/account/financial action) and *when* to escalate — do **not** write "always call get_customer first." Keep escalation/handoff guidance minimal here (fleshed out Phase 3).

---

## IMPLEMENTATION PLAN

### Phase 1 (this plan) — Foundation: Loop + Tools

**Tasks:** scaffold the package and deps; build the mock backend + fixtures; define the four MCP tools with rich descriptions; build the agent options + system prompt; build the loop helper; write the order-status validation suite.

> Phases 2–4 below are out of scope for this plan; listed only so the foundation is shaped to receive them.

### Phase 2 (later) — Guardrails
PreToolUse refund-limit hook (TR3), prerequisite gate (TR4), PostToolUse date normalization (TR5).

### Phase 3 (later) — Errors + Escalation
Structured errors (TR6), escalation calibration + few-shots (TR7), handoff JSON (TR8), turn on the flaky-503 endpoint.

### Phase 4 (later) — Context + Multi-issue
Case-facts block (TR9), output trimming, multi-issue decomposition.

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task is atomic and independently validatable. The Python interpreter is the **shared workspace venv**: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python` (referred to below as `$PY`). All commands run from the project root `projects/customer-support/`.

### Task 1 — CREATE dependency manifest + install

- **IMPLEMENT**: Create `requirements.txt` listing `claude-agent-sdk`, `pytest`, `pytest-asyncio`, `python-dotenv`. Install into the shared venv.
- **IMPORTS**: n/a.
- **GOTCHA**: The shared venv currently has only `anthropic` + `voyageai`. Do **not** create a new venv — install into the existing shared one. **The `claude-agent-sdk` Python package historically launches the Claude Code CLI as a subprocess and requires Node.js + `@anthropic-ai/claude-code` installed.** Confirm this is satisfied before assuming tools run (the environment notes Claude Code CLI is available, so it likely is). If the SDK errors at runtime about a missing CLI/binary, that's this dependency.
- **VALIDATE**:
  ```bash
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/pip install -r requirements.txt && \
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "import claude_agent_sdk, pytest, dotenv; print(claude_agent_sdk.__version__)"
  ```

### Task 2 — VALIDATE SDK API surface (do this before writing tool/loop code)

- **IMPLEMENT**: Confirm the exact names against the installed version: `tool`, `create_sdk_mcp_server`, `ClaudeAgentOptions`, `query`, and message classes (`AssistantMessage`, `ResultMessage`, `SystemMessage`, `ToolUseBlock`, `TextBlock`). Confirm `ClaudeAgentOptions` field names: `system_prompt`, `model`, `mcp_servers`, `allowed_tools`, `max_turns`. Confirm the `@tool` signature and the tool return-dict keys (`content`, `is_error`, `structuredContent`).
- **GOTCHA**: This plan was seeded from documentation the research step could not fully verify against GitHub. Treat the shapes here as the *intended* design; if a symbol/field differs in the installed version, adapt and note it. The Phase-1 surface (tools, options, query, message types) is the stable core — hooks are not needed until Phase 2.
- **VALIDATE**:
  ```bash
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "import claude_agent_sdk as s; print([n for n in dir(s) if not n.startswith('_')])"
  ```

### Task 3 — CREATE `src/config.py`

- **IMPLEMENT**: Load the workspace `.env` (path `../../.env` relative to project root → `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.env`) via `python-dotenv`. Export constants: `MODEL = "claude-opus-4-8"`, `MAX_TURNS_BACKSTOP = 20`, `MCP_SERVER_NAME = "support"`, `REFUND_POLICY_LIMIT = 500.0` (unused in Phase 1; defined here so Phase 2's hook imports one source of truth).
- **PATTERN**: keep constants module-level; provide `load_env()` that's idempotent and called from `agent.py`/`conftest.py`.
- **IMPORTS**: `import os`, `from pathlib import Path`, `from dotenv import load_dotenv`.
- **GOTCHA**: `.env` is at the **workspace root** (two levels up), not the project root. Compute the path from `__file__`, don't assume CWD.
- **VALIDATE**:
  ```bash
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config; config.load_env(); import os; print('KEY_PRESENT', bool(os.environ.get('ANTHROPIC_API_KEY')))"
  ```

### Task 4 — CREATE `src/mocks/fixtures.py`

- **IMPLEMENT**: In-memory seed data + accessor functions:
  - **Customers** (dicts keyed by `customer_id`): `C001` Alice Wong (alice@example.com, 555-0101); `C002` Bob Martinez (bob@example.com, 555-0102); **duplicate-name pair** `C003` John Smith (john.smith@example.com) and `C004` John Smith (jsmith2@example.com).
  - **Orders** (keyed by `order_id`, each with `customer_id`, `status`, `total`, and a `placed_at` in a **deliberately heterogeneous** format): `O1001` → C001, status `"shipped"`, total `42.00`, `placed_at` as a **Unix timestamp** (int); `O1002` → C002, status `"delivered"`, total `900.00` (sets up the Phase-2 over-limit refund case), `placed_at` as `"Mar 5, 2025"`; `O1003` → C001, status `"processing"`, total `120.00`, `placed_at` as ISO 8601 `"2025-03-15T14:30:00Z"`.
  - **Accessors**: `find_customers(*, name=None, email=None, phone=None) -> list[dict]` (returns 0/1/many — the John Smith pair returns 2 for name="John Smith"); `get_order(order_id) -> dict | None`; `FLAKY_503_ENABLED = False` flag + a `maybe_fail_transient()` no-op stub for Phase 3 (keep it inert in Phase 1 so tests are deterministic).
- **PATTERN**: pure data + pure functions; no SDK imports here (keeps the backend testable in isolation).
- **GOTCHA**: Keep the heterogeneous date formats — they are intentional setup for TR5 (Phase 2). Do not normalize them in the fixture. Phase 1 order-status answers may surface the raw date; that's acceptable now.
- **VALIDATE**:
  ```bash
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from mocks import fixtures as f; print(len(f.find_customers(name='John Smith')), f.get_order('O1001')['status'])"
  ```
  Expect: `2 shipped`.

### Task 5 — CREATE `src/tools/server.py` (the four MCP tools, TR2)

- **IMPLEMENT**: Four `async @tool` handlers wrapping the mock accessors, then `create_sdk_mcp_server(name="support", version="1.0.0", tools=[...])`. **Rich, disambiguating descriptions** are the deliverable here — purpose, input formats, example values, edge cases, and explicit "use this vs the other tool" guidance for the two similar tools.
  - `get_customer(args)` — input `{name?, email?, phone?}` (at least one). **Description must say**: "Identifies/verifies a *customer* by personal identifiers (name, email, or phone). Use this FIRST to establish who you are talking to, before any order or account action. Returns one match, multiple matches (ask the user for an additional identifier — never guess), or none. Do NOT use this to fetch order details — use `lookup_order` for that." Returns `structuredContent` with matched customer id(s) + minimal fields.
  - `lookup_order(args)` — input `{customer_id, order_id}`. **Description must say**: "Fetches the details/status of a specific *order* for an already-verified customer. Requires a `customer_id` obtained from `get_customer`. Use this to answer order-status / tracking / contents questions — NOT to find or verify a person." Returns order status, total, date.
  - `process_refund(args)` — input `{customer_id, order_id, amount, reason?}`. Description states it issues a refund within policy and that large/out-of-policy refunds are routed to a human (enforcement is Phase 2 — no hook yet). Returns a confirmation stub.
  - `escalate_to_human(args)` — input `{customer_id?, order_id?, reason}` (full handoff schema is Phase 3). Returns an acknowledgement stub.
- **PATTERN**: every handler returns the standard shape (see Patterns). On a not-found, return `is_error: False` with an explanatory `content` text for Phase 1 (structured `errorCategory` is Phase 3).
- **IMPORTS**: `from claude_agent_sdk import tool, create_sdk_mcp_server`; `from mocks import fixtures`.
- **GOTCHA**: Tool *names* must be exactly the four spec names. The two similar tools (`get_customer` vs `lookup_order`) must be separable **by description alone** — this is explicitly graded (TR2). Don't lean on the system prompt to disambiguate.
- **VALIDATE**:
  ```bash
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from tools import server; print(server.support_server is not None)"
  ```

### Task 6 — CREATE `src/agent.py` (options + system prompt)

- **IMPLEMENT**: `build_options() -> ClaudeAgentOptions` with `model=config.MODEL`, `mcp_servers={"support": support_server}`, `allowed_tools=["mcp__support__get_customer", "mcp__support__lookup_order", "mcp__support__process_refund", "mcp__support__escalate_to_human"]`, `max_turns=config.MAX_TURNS_BACKSTOP`, and `system_prompt=SYSTEM_PROMPT`. Write `SYSTEM_PROMPT` focused on **behavior**: resolve common support intents; **verify the customer's identity before any order, account, or financial operation**; if `get_customer` returns multiple matches, ask for another identifier rather than guessing; escalate on explicit human requests or policy gaps. Do **not** instruct "always call get_customer on every turn."
- **PATTERN**: keep the prompt concise; behavior + escalation judgment only.
- **IMPORTS**: `from claude_agent_sdk import ClaudeAgentOptions`; `from tools.server import support_server`; `from . import config` (or `import config` depending on how the package is run — confirm import style in Task 2 smoke test).
- **GOTCHA**: List exactly the four `mcp__support__*` names (least privilege, D2.3). A wildcard `mcp__support__*` is acceptable but explicit names are preferred for the audit story. Confirm the option field is `system_prompt` (not `system`) for this SDK.
- **VALIDATE**:
  ```bash
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config; config.load_env(); from agent import build_options; o=build_options(); print(o.allowed_tools)"
  ```

### Task 7 — CREATE `src/loop.py` (TR1 loop helper)

- **IMPLEMENT**: An async `run_turn(prompt: str, options) -> AgentRun` where `AgentRun` is a small dataclass: `tool_calls: list[str]` (fully-qualified or bare tool names, in call order), `final_text: str`, `subtype: str` (from `ResultMessage`), `terminated_by_result: bool`. Iterate `query(prompt=prompt, options=options)`; on `AssistantMessage`, append any `ToolUseBlock.name`s to `tool_calls` and capture text; on `ResultMessage`, record `subtype`/result and stop.
- **PATTERN**: **Termination is by message type / `ResultMessage`, never by scanning text.** Record whether the terminal `subtype` was a success vs `max_turns`-style outcome so tests can assert the cap was not the primary stop.
- **IMPORTS**: `from claude_agent_sdk import query, AssistantMessage, ResultMessage, ToolUseBlock, TextBlock` (confirm exact class names in Task 2).
- **GOTCHA**: `ToolUseBlock.name` for an SDK MCP tool may be the fully-qualified `mcp__support__get_customer` — normalize to the bare tool name (strip the `mcp__support__` prefix) so assertions read cleanly, but keep the raw name available. Tool inputs may be JSON-escaped — never raw-string-match them; use the parsed `.input`.
- **VALIDATE**: covered by Task 8's live test (needs an API call).

### Task 8 — CREATE `tests/conftest.py` + `tests/test_phase1_order_status.py`

- **IMPLEMENT**:
  - `conftest.py`: call `config.load_env()`; provide a `run_agent` fixture/helper that wraps `run_turn(build_options())`; configure `pytest-asyncio`. Add a module-level skip if `ANTHROPIC_API_KEY` is absent so the suite fails gracefully without creds.
  - `test_phase1_order_status.py`:
    1. **Happy path / E2E + tool selection** — prompt: `"Hi, I'm Alice Wong (alice@example.com). What's the status of my order O1001?"`. Assert: `get_customer` is in `tool_calls`; `lookup_order` is in `tool_calls`; `get_customer` is called **before** `lookup_order`; the final result `subtype == "success"`; `terminated_by_result is True`. (Outcome/behavior assertions — NOT asserting exact wording. A light, case-insensitive substring check for `"shipped"` in `final_text` is acceptable as a resolution signal but keep it lenient.)
    2. **Loop terminates on completion, not the cap** — assert the terminal `subtype` is the success value and is **not** the `max_turns` variant (TR1 anti-pattern guard).
    3. **Correct-tool disambiguation** — assert the agent used `lookup_order` (not a second `get_customer`) to fetch the order details, demonstrating the two similar tools are distinguished.
- **PATTERN**: assert on `tool_calls` order/membership and `subtype` — the spec's "ground truth = tool calls and outcomes, not prose." Mark these as integration tests (they hit the live API).
- **IMPORTS**: `pytest`, `from loop import run_turn`, `from agent import build_options`.
- **GOTCHA**: These tests make **real API calls** and depend on model behavior, so allow for minor nondeterminism: assert on tool *membership and ordering*, not on call counts being exactly N or on exact phrasing. If the model occasionally answers without `lookup_order`, that's a system-prompt/tool-description quality signal to fix in Task 5/6 — not a reason to weaken the assertion to nothing.
- **VALIDATE**:
  ```bash
  cd /Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/customer-support && \
  /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -m pytest tests/ -v
  ```

### Task 9 — VALIDATE end-to-end + clean up imports

- **IMPLEMENT**: Run the full suite; confirm no import-path issues (the `src/` layout requires either running pytest from the project root with `src` on the path via `pytest.ini`/`conftest` `sys.path` insert, or installing the package editable). Pick one approach and make it consistent.
- **GOTCHA**: Mixing `from . import config` (package-relative) with `import config` (path-insert) will break depending on how pytest collects. Standardize: simplest for a shared-venv greenfield is a `conftest.py` `sys.path.insert(0, "src")` + absolute imports (`import config`, `from tools.server import ...`). Confirm and apply uniformly.
- **VALIDATE**: the Task 8 pytest command passes green.

---

## TESTING STRATEGY

Test framework: **pytest** (per global rules; no existing `tests/` dir, so this creates it). Ground truth = **tool calls + outcomes, not prose** (spec Validation Strategy).

### Unit Tests
- `src/mocks/fixtures.py` is pure and unit-testable without the API: assert `find_customers(name="John Smith")` returns 2 (duplicate pair), unique lookups return 1, unknown returns 0; `get_order` returns the right record and `None` for unknown ids. (Add a small `tests/test_fixtures.py` — fast, no API key needed.)

### Integration Tests
- The order-status E2E in `test_phase1_order_status.py` (Task 8) — live API, asserts tool selection, ordering, and `ResultMessage.subtype == success`.

### Edge Cases (Phase 1 scope)
- Order-status for a customer identified by **email** vs **name** (both should verify then look up).
- The model does **not** loop forever / does not stop via `max_turns` on the happy path (TR1 backstop guard).
- (Deferred to later phases, but fixtures are ready: duplicate-name → ask-for-identifier (Phase 3), over-limit refund on O1002 (Phase 2), heterogeneous dates (Phase 2).)

---

## VALIDATION COMMANDS

Run from `projects/customer-support/`. `$PY = /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python`.

### Level 1: Syntax & Style
```bash
/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -m py_compile src/config.py src/agent.py src/loop.py src/tools/server.py src/mocks/fixtures.py
# Optional if installed: ruff check src tests  &&  black --check src tests
```

### Level 2: Unit Tests (no API key needed)
```bash
/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -m pytest tests/test_fixtures.py -v
```

### Level 3: Integration Tests (requires ANTHROPIC_API_KEY from ../../.env)
```bash
/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -m pytest tests/test_phase1_order_status.py -v
```

### Level 4: Manual Validation
```bash
# Minimal smoke driver: resolve one order-status query and print tool calls + result.
/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python -c "
import asyncio, sys; sys.path.insert(0,'src')
import config; config.load_env()
from loop import run_turn; from agent import build_options
run = asyncio.run(run_turn(\"I'm Alice Wong, alice@example.com — status of order O1001?\", build_options()))
print('TOOLS:', run.tool_calls); print('SUBTYPE:', run.subtype); print('TEXT:', run.final_text[:200])
"
```

### Level 5: Additional Validation (Optional)
- Re-run the integration test 3× to gauge behavioral stability of tool selection (acceptable: tool membership/order consistent; wording varies).

---

## ACCEPTANCE CRITERIA (Phase 1)

- [ ] `claude-agent-sdk`, `pytest`, `pytest-asyncio`, `python-dotenv` installed into the shared venv; import smoke test passes.
- [ ] Exactly **four** MCP tools defined with the exact spec names and **rich, disambiguating descriptions**; `get_customer` and `lookup_order` are separable by description alone.
- [ ] `allowed_tools` scopes the agent to exactly those four `mcp__support__*` tools (least privilege).
- [ ] An order-status query resolves **end-to-end**: agent calls `get_customer` then `lookup_order`, and returns the order's status.
- [ ] The loop terminates on the SDK's `ResultMessage` success outcome — **not** by parsing assistant text and **not** because `max_turns` was hit (verified by assertion).
- [ ] System prompt is behavior/escalation-focused and does **not** hard-couple `get_customer` to every turn.
- [ ] Fixtures include the duplicate-name pair and heterogeneous order-date formats (staged for Phases 2–3), with the flaky-503 path inert in Phase 1.
- [ ] Unit tests (fixtures) and the integration test (order-status) pass.
- [ ] Code follows project conventions; no leftover guessed API names (all validated against the installed SDK in Task 2).

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order; each task's VALIDATE passed before moving on.
- [ ] Level 1–3 validation commands pass; Level 4 smoke driver prints `get_customer` + `lookup_order` and a `success` subtype.
- [ ] No `py_compile`/import errors; import style standardized (Task 9).
- [ ] Acceptance criteria all met.
- [ ] Any SDK API deviations from this plan documented inline (comment or a note appended to this file) for Phase 2's hook work.

---

## NOTES

**Design decisions & trade-offs**
- **Agent SDK over raw Messages API** (decided with the user). Consequence carried into every phase: TR1's literal `stop_reason` state machine is satisfied *in intent* — the SDK runs the loop and exposes `ResultMessage`/`subtype` rather than a raw `stop_reason`. The acceptance test asserts on that terminal outcome and that `max_turns` was not the cause. Recorded in project memory `cs-agent-sdk-decision`.
- **All four tools created now, hooks deferred.** `process_refund`/`escalate_to_human` exist with stub behavior so the tool surface and `allowed_tools` are final from Phase 1; the deterministic guardrails (PreToolUse refund gate, prerequisite gate, PostToolUse normalization) attach in Phase 2 without re-shaping the tools.
- **Fixtures pre-stage later phases** (duplicate-name pair, heterogeneous dates, 503 flag) so no fixture churn later — but those paths are inert/untested in Phase 1 to keep this suite deterministic.

**Key risks / things the execution agent must verify first**
1. **`claude-agent-sdk` install prerequisites** — likely needs the Claude Code CLI / Node runtime as a subprocess backend. If tool calls fail at runtime with a missing-binary error, that's the cause (Task 1 GOTCHA).
2. **Exact SDK symbol/field names** — this plan was seeded from docs that couldn't be fully verified against source. Task 2 validates the real surface before any tool/loop code is written. The fields most worth confirming: `ClaudeAgentOptions.system_prompt` vs `system`, the `@tool` signature, the tool return-dict keys, and `ToolUseBlock.name` prefixing.
3. **Model ID** — use `claude-opus-4-8` (the seeding research suggested stale IDs).
4. **Behavioral test flakiness** — integration assertions target tool membership/ordering + outcome, not wording or exact counts; if tool selection is unstable, fix the tool descriptions/system prompt rather than weakening assertions.

**Confidence (one-pass success): 7/10.** The structure, fixtures, tests, and validation gates are concrete and low-risk. The point deduction is entirely the unverified-against-source SDK API details (Task 2 exists precisely to de-risk this) and the CLI/Node subprocess dependency — if either bites, it costs a short detour, not a redesign.

---

## EXECUTION NOTES (Phase 1 complete — verified against `claude-agent-sdk` 0.2.110)

All acceptance criteria met; 14 tests pass (10 unit, 4 live integration). SDK API surface confirmed against the installed version — the plan's intended shapes were accurate. Carry these verified facts into Phase 2:

1. **SDK API surface — all confirmed as planned.** `tool(name, description, input_schema)`, `create_sdk_mcp_server(name, version, tools=[...])`, `query(prompt=, options=)`, `ClaudeAgentOptions` fields `system_prompt`/`model`/`mcp_servers`/`allowed_tools`/`max_turns`, and message classes `AssistantMessage`/`ResultMessage`/`ToolUseBlock`/`TextBlock` all exist with those exact names. Tool return shape is `{"content": [...], "is_error": bool}` (+ optional `structuredContent`). `input_schema` accepts a full JSON-Schema dict (detected when the dict has a string `"type"` + `"properties"`), which we use to mark optional params.
2. **`ToolUseBlock.name` is the fully-qualified `mcp__support__<tool>`** — `loop.py` strips the prefix to a bare name for clean assertions, keeping the raw name too.
3. **`ResultMessage` exposes `subtype` (e.g. `"success"`) AND `stop_reason`, `is_error`, `num_turns`, `result`.** The loop finishes on `ResultMessage`; `terminated_by_cap` checks `"max_turns" in subtype`. TR1 satisfied in intent (no text-parsing; cap is backstop only).
4. **Auth: the workspace `.env` `ANTHROPIC_API_KEY` is EMPTY, but live runs still succeed** — the SDK drives the `claude` CLI subprocess, which authenticates via the user's Claude Code login. Integration tests gate on `shutil.which("claude")`, not the env var.
5. **Two added options for least privilege + determinism (not in the original plan):** `tools=[]` strips the CLI's built-in tools so the agent's entire toolset is the four MCP tools, AND keeps the registry small enough that the CLI does NOT defer tools behind a `ToolSearch` discovery step (without this, an extra `ToolSearch` tool call appeared and added a turn). `strict_mcp_config=True` ignores ambient MCP config. **Phase 2 hooks must keep these.**
6. **Loop cleanup gotcha:** do NOT `break` out of the `query()` async-for early — tearing down the generator while its subprocess reader task is live raises `aclose(): asynchronous generator is already running`. The loop records the first `ResultMessage` and drains the stream to natural completion.
7. **`setting_sources` defaults to `None`** in this SDK (only forced to `["user","project"]` when skills are used), so user/project settings are NOT loaded — the `ToolSearch` artifact was CLI tool-deferral, not leaked settings.

**Files created:** `requirements.txt`, `pytest.ini`, `src/{__init__,config,agent,loop}.py`, `src/tools/{__init__,server}.py`, `src/mocks/{__init__,fixtures}.py`, `tests/{__init__,conftest}.py`, `tests/test_fixtures.py`, `tests/test_phase1_order_status.py`.
