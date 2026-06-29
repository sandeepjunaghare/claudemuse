# Feature: Customer Support Resolution Agent — Phase 2 (Deterministic Guardrails)

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing. **Pay special attention to the exact `claude-agent-sdk` 0.2.110 hooks API surface** (introspected and recorded below — do not re-guess), and to importing from the right modules. Phase 1's load-bearing options (`tools=[]`, `strict_mcp_config=True`) **must be preserved**.

## Feature Description

Add the three **deterministic guardrails** that are the entire point of this build — rules that must hold 100% of the time, implemented as **SDK hooks / code, never as system-prompt instructions**:

- **TR3 — Refund limit:** a **PreToolUse hook** intercepts `process_refund` and **denies** any amount over the policy limit (`$500`), returning a reason that routes the agent to escalate. The deny is the provable-100% guarantee; the agent's escalation is its calibrated response to the block.
- **TR4 — Prerequisite gate:** a **PreToolUse hook** blocks `lookup_order` and `process_refund` unless the `customer_id` argument was **verified this session** — where "verified" means a prior `get_customer` call returned **exactly one** match. Multiple matches do NOT verify (preserves the TR7 disambiguation path).
- **TR5 — Date normalization:** a **PostToolUse hook** on `lookup_order` rewrites the heterogeneous `placed_at` value (Unix int / `"Mar 5, 2025"` / ISO 8601) to canonical ISO 8601 **before the model reasons over it**, using the SDK's `updatedMCPToolOutput`.

The four tools, the loop, the mock fixtures, and the behavior-focused system prompt from Phase 1 are **unchanged in shape** — guardrails attach *around* the loop via `ClaudeAgentOptions(hooks=...)`. The system prompt is NOT touched to add any of these rules (doing so would be an automatic failure of the deterministic-vs-probabilistic thesis).

## User Story

As **the retail business (and the customer)**
I want **every refund over policy blocked in code, every order/refund action gated behind verified identity, and every order date normalized to one format**
So that **no large refund is ever issued autonomously, no action is ever taken on an unverified customer, and the agent never mis-reasons over inconsistent date formats — guaranteed by code, not by hoping the model obeys a prompt.**

## Problem Statement

Phase 1 stood up a working loop and four tools, but `process_refund` will happily refund any amount, `lookup_order`/`process_refund` will run against any `customer_id` the model supplies (verified or hallucinated), and `lookup_order` returns dates in three incompatible formats. These are exactly the invariants the spec says must be **deterministic**. A prompt instruction ("don't refund over $500", "always verify first") is explicitly called out as an automatic failure (CLAUDE.md, PRD §2.1, TR3). They must be enforced in hooks/code with a test suite that proves the guarantee across many cases without depending on model wording or behavior.

## Solution Statement

Wire `claude-agent-sdk` hooks into `build_options()`:

- **PreToolUse** matchers on `process_refund` (refund gate, TR3) and on `lookup_order|process_refund` (prerequisite gate, TR4). A hook returning `permissionDecision: "deny"` stops the tool from executing and feeds `permissionDecisionReason` back to the model.
- **PostToolUse** matchers on `get_customer` (record the verified customer id into a per-session store, feeding TR4) and on `lookup_order` (normalize `placed_at` via `updatedMCPToolOutput`, TR5).

A tiny in-process, **session-keyed** `verified_store` bridges the `get_customer` PostToolUse hook (writer) and the prerequisite PreToolUse hook (reader). Date normalization logic lives in a **pure, SDK-free function** so it's unit-testable in isolation.

Validation is split per the locked design decisions: **deterministic hook unit tests** (call the hook callables directly with synthetic payloads — fast, free, truly 100%-provable across 20+ amounts and the gate) plus **a few live integration tests** for end-to-end behavior (block→escalate, ISO dates in the answer, verified-then-lookup).

## Feature Metadata

**Feature Type**: Enhancement (adds enforcement layer to the Phase 1 foundation)
**Estimated Complexity**: Medium
**Primary Systems Affected**: `src/hooks/` (new package), `src/agent.py` (wire hooks), `tests/` (new deterministic + live suites)
**Dependencies**: No new packages. Uses `claude-agent-sdk` 0.2.110 hooks (already installed) and Python stdlib `datetime` only (deliberately avoid adding `python-dateutil`).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `CLAUDE.md` (project root) — the deterministic-vs-probabilistic thesis. TR3/TR4/TR5 bullets state *exactly* what must be code vs. prompt. Re-read before touching anything.
- `.agents/plans/customer-support-phase-1.md` (lines 318–331, **EXECUTION NOTES**) — verified SDK facts: tool names are fully-qualified `mcp__support__<tool>`; `tools=[]` + `strict_mcp_config=True` are load-bearing (keep them); CLI-auth (empty env key still works); do NOT `break` the `query()` async-for early.
- `src/agent.py` (lines 47–65, `build_options`) — the function to extend with `hooks=`. Do not alter `tools=[]`, `strict_mcp_config=True`, `allowed_tools`, or `SYSTEM_PROMPT`. The system prompt stays behavior-only; add nothing about limits/verification/dates.
- `src/config.py` (line 26, `REFUND_POLICY_LIMIT = 500.0`) — the single source of truth for TR3. Import it; never hardcode 500.
- `src/tools/server.py`:
  - lines 28–34 (`_result`) and 63–88 (`get_customer`) — the tool return shape is `{"content":[{"type":"text","text":...}], "structuredContent": {...}, "is_error": bool}`. `get_customer`'s `structuredContent` is `{"matchCount": N, "matches": [{"id","name","email"}]}` — this is what the get_customer PostToolUse hook reads to detect a single verified match.
  - lines 115–145 (`lookup_order`) — `structuredContent` has `placedAt` (the field TR5 normalizes) plus the human-readable `content` text `"... placed {placed_at}."`. Both must be normalized.
- `src/mocks/fixtures.py` (lines 24–31, `ORDERS`) — the three heterogeneous `placed_at` values the normalizer must handle: `1740787200` (Unix int → 2025-03-01T00:00:00Z), `"Mar 5, 2025"` (human string), `"2025-03-15T14:30:00Z"` (ISO). O1002's `$900.00` total is the over-limit refund case; it belongs to C002.
- `tests/conftest.py` (lines 14–44) — `sys.path.insert(0, "src")` + absolute imports; `agent_runnable()` gates live tests on `shutil.which("claude")`; `run_agent` fixture. Mirror this for new tests.
- `tests/test_phase1_order_status.py` (lines 9–22) — the live-test skip pattern (`pytestmark` with `integration` marker + skipif) and the assert-on-`tool_calls`/`subtype` style. Mirror exactly.
- `tests/test_fixtures.py` — the no-API unit-test style; mirror for the pure-function date tests.
- `pytest.ini` — confirm `asyncio_mode` and registered markers (`integration`) before adding tests.

### New Files to Create

- `src/hooks/__init__.py` — package marker.
- `src/hooks/verified_store.py` — per-session verified-customer registry: `mark_verified(session_id, customer_id)`, `is_verified(session_id, customer_id) -> bool`, `reset(session_id=None)`. Pure Python, no SDK import.
- `src/hooks/normalize.py` — **pure** `to_iso8601(value) -> str` (SDK-free, unit-testable) **and** the `normalize_order_dates` PostToolUse hook wrapper (TR5).
- `src/hooks/refund_gate.py` — `refund_gate` PreToolUse hook (TR3).
- `src/hooks/prerequisite_gate.py` — `prerequisite_gate` PreToolUse hook (TR4) + `record_verified_customer` PostToolUse hook (writes the store from `get_customer` results).
- `tests/test_hooks_refund_gate.py` — deterministic, no API: 20+ amounts across/under/at the limit.
- `tests/test_hooks_prerequisite_gate.py` — deterministic, no API: gate denies pre-verification, allows post-verification, multi-match never verifies, store session isolation.
- `tests/test_hooks_normalize.py` — deterministic, no API: `to_iso8601` for all three fixture formats + unparseable passthrough; hook rewrites `structuredContent.placedAt` and `content` text.
- `tests/test_phase2_guardrails_live.py` — a few live integration tests (block→escalate, verified-then-lookup, ISO date surfaced).

### Files to Update

- `src/agent.py` — add `from claude_agent_sdk import HookMatcher` and a `_build_hooks()` helper; pass `hooks=_build_hooks()` into `ClaudeAgentOptions(...)`.

### Relevant Documentation — READ THESE BEFORE IMPLEMENTING

- [Claude Agent SDK — Hooks (Python)](https://platform.claude.com/docs/en/agent-sdk/hooks) — PreToolUse/PostToolUse events, `HookMatcher`, callback signature, `permissionDecision` / `updatedMCPToolOutput`. **Primary reference for this phase.**
- [Claude Code Hooks reference](https://docs.anthropic.com/en/docs/claude-code/hooks#structure) — the `matcher` string semantics (tool name or `A|B` alternation), referenced directly in the SDK's `HookMatcher` docstring.
- The SDK type module is the **ground truth** (installed at `…/.venv/.../claude_agent_sdk/types.py`). The exact shapes below were introspected from it — trust them over external docs if they ever diverge.

### Verified SDK Hooks API surface (introspected from `claude_agent_sdk` 0.2.110 — do NOT re-guess)

```python
# ClaudeAgentOptions field:
hooks: dict[HookEvent, list[HookMatcher]] | None = None
#   HookEvent is a string literal: "PreToolUse", "PostToolUse", "PostToolUseFailure",
#   "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact", "Notification", ...

# HookMatcher(matcher: str | None = None, hooks: list[HookCallback] = [], timeout: float | None = None)
#   matcher: tool-name string, e.g. "mcp__support__process_refund", or an alternation
#            like "mcp__support__lookup_order|mcp__support__process_refund".
#            matcher=None matches ALL tools. (See GOTCHA on matcher semantics.)

# HookCallback signature (async):
#   async def cb(input: dict, tool_use_id: str | None, context: dict) -> dict
#   - input is a TypedDict-shaped dict. Access via input["..."]. Relevant keys:
#       PreToolUse:  hook_event_name, tool_name, tool_input(dict), tool_use_id, session_id, cwd, transcript_path
#       PostToolUse: hook_event_name, tool_name, tool_input(dict), tool_response(Any), tool_use_id, session_id, ...
#     (session_id comes from BaseHookInput — use it to key per-run state.)
#   - context is HookContext: {"signal": None}  (placeholder; ignore)

# RETURN VALUES (plain dicts):
#   Allow / no opinion:   {}
#   PreToolUse deny:      {"hookSpecificOutput": {"hookEventName": "PreToolUse",
#                            "permissionDecision": "deny",
#                            "permissionDecisionReason": "<fed back to the model>"}}
#       (permissionDecision options: "allow" | "deny" | "ask" | "defer")
#   PreToolUse modify input: add "updatedInput": {...} under hookSpecificOutput (NOT needed this phase)
#   PostToolUse rewrite output: {"hookSpecificOutput": {"hookEventName": "PostToolUse",
#                            "updatedMCPToolOutput": <replacement tool result>}}
#       ("updatedMCPToolOutput" replaces an MCP tool's output before the model sees it;
#        "updatedToolOutput" is the built-in-tool equivalent — we use updatedMCPToolOutput.)
#       PostToolUse can also add "additionalContext": str (append-only) — we use rewrite, not append.
```

### Patterns to Follow

**Naming Conventions:** `snake_case` functions/modules; hook callables named for their job (`refund_gate`, `prerequisite_gate`, `record_verified_customer`, `normalize_order_dates`). Match Phase 1's concise module-docstring + per-function-docstring style, with `(TRn)` tags tying code to requirements.

**Hook callback shape (mirror in every hook):**
```python
async def some_hook(input: dict, tool_use_id, context) -> dict:
    """One-line purpose (TRn)."""
    # Defensive: re-check the tool name even though the matcher should scope us
    # (matcher regex semantics are not 100% guaranteed — see GOTCHA).
    if not input.get("tool_name", "").endswith("<bare_tool_name>"):
        return {}
    ...
    return {}  # or a hookSpecificOutput dict
```

**Fully-qualified tool names:** `mcp__support__get_customer`, `mcp__support__lookup_order`, `mcp__support__process_refund`. Match on the bare suffix inside hooks (`.endswith("process_refund")`) so a prefix change can't silently disable a guardrail.

**Deny reason = routing instruction:** `permissionDecisionReason` is read by the model. Phrase it as an actionable instruction ("…exceeds the policy limit; escalate via escalate_to_human") so the block naturally produces the calibrated escalation (TR3 decision: block is the guarantee, model escalates).

**Test style:** deterministic hook tests call the hook callable via `asyncio.run(hook(synthetic_input, "tu_1", {"signal": None}))` and assert on the returned dict — no API, no markers. Live tests carry `pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _runnable, ...)]` exactly like `test_phase1_order_status.py`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
Establish the per-session verified-customer store and the pure date-normalization function — both SDK-free and independently unit-testable — before any hook wiring.

### Phase 2: Core Implementation (the hooks)
Implement the four hook callables: `refund_gate` (TR3), `prerequisite_gate` + `record_verified_customer` (TR4), `normalize_order_dates` (TR5).

### Phase 3: Integration
Wire the hooks into `build_options()` via `HookMatcher`s, preserving Phase 1's options. Smoke-test that hooks actually fire and confirm the real `tool_response` shape.

### Phase 4: Testing & Validation
Deterministic unit suites (refund gate ×20+ amounts, prerequisite gate, normalization) + a small live integration suite. Confirm the Phase 1 suite still passes (no regressions).

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. `$PY = /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python`. All commands run from the project root `projects/customer-support/`.

### Task 0 — VALIDATE hooks fire + capture the real `tool_response` shape (do this FIRST)

- **IMPLEMENT**: Before writing real hooks, run a throwaway smoke driver that registers a trivial PreToolUse hook (matcher `mcp__support__get_customer`) that returns `{}` and a PostToolUse hook that **prints `input["tool_name"]` and `repr(input["tool_response"])`**, then runs one `get_customer` query. The goal is to confirm (a) hooks fire for in-process MCP tools, (b) the `matcher` string matches the fully-qualified name, and (c) the exact runtime shape of `tool_response` (is it the raw `{"content":..., "structuredContent":..., "is_error":...}` dict, or wrapped/list-ified by the MCP layer?). This shape drives Tasks 2, 4, 5.
- **PATTERN**: reuse the Level-4 smoke-driver shape from the Phase 1 plan (sys.path insert, `config.load_env()`, `asyncio.run`). Build `ClaudeAgentOptions` like `build_options()` but with the temp hooks.
- **IMPORTS**: `from claude_agent_sdk import HookMatcher, query, ClaudeAgentOptions`.
- **GOTCHA**: This makes a live API call (needs the `claude` CLI). If `tool_response` is **not** the bare tool dict (e.g. it's `{"content":[{"type":"text","text":"<json>"}]}` with `structuredContent` elsewhere, or a list), record the actual access path and adjust `_extract_structured()` (Task 4) and the normalizer (Task 5) accordingly. **Do not assume — verify and write the observed shape into a comment in `prerequisite_gate.py`.**
- **VALIDATE**:
  ```bash
  $PY -c "
  import asyncio, sys; sys.path.insert(0,'src')
  import config; config.load_env()
  from claude_agent_sdk import HookMatcher, query, ClaudeAgentOptions
  from tools.server import support_server
  seen=[]
  async def post(i,t,c):
      print('POST tool_name=', i.get('tool_name')); print('POST tool_response=', repr(i.get('tool_response'))[:800]); seen.append(i); return {}
  async def pre(i,t,c):
      print('PRE tool_name=', i.get('tool_name'), 'session=', i.get('session_id')); return {}
  opts=ClaudeAgentOptions(model=config.MODEL, system_prompt='Identify the customer.', tools=[], mcp_servers={config.MCP_SERVER_NAME: support_server}, allowed_tools=['mcp__support__get_customer'], strict_mcp_config=True, max_turns=5, hooks={'PreToolUse':[HookMatcher(matcher='mcp__support__get_customer', hooks=[pre])],'PostToolUse':[HookMatcher(matcher='mcp__support__get_customer', hooks=[post])]})
  async def main():
      async for m in query(prompt='Look up customer Alice Wong (alice@example.com).', options=opts): pass
  asyncio.run(main()); print('HOOKS_FIRED=', len(seen)>0)
  "
  ```
  Expect `HOOKS_FIRED= True` and a printed `tool_response`. **Record the structuredContent access path.**

### Task 1 — CREATE `src/hooks/__init__.py` + `src/hooks/verified_store.py`

- **IMPLEMENT**:
  - `__init__.py`: empty package marker (match `src/tools/__init__.py`).
  - `verified_store.py`: a module-level `dict[str, set[str]]` keyed by `session_id` → set of verified `customer_id`s.
    - `mark_verified(session_id: str, customer_id: str) -> None`
    - `is_verified(session_id: str, customer_id: str) -> bool`
    - `reset(session_id: str | None = None) -> None` — clears one session, or all when `None` (used by the test reset fixture).
- **PATTERN**: pure data + pure functions, no SDK import (mirror `src/mocks/fixtures.py`'s SDK-free discipline so it unit-tests without the API).
- **IMPORTS**: stdlib only.
- **GOTCHA**: Keying by `session_id` is what prevents state leaking across the 20+ live cases and across unit tests. The store is process-global; tests MUST call `reset()` between cases (provide an autouse fixture in conftest or per-test). Treat a missing/empty `session_id` as its own bucket (`""`) — don't crash.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); from hooks import verified_store as v; v.mark_verified('s1','C001'); print(v.is_verified('s1','C001'), v.is_verified('s1','C002'), v.is_verified('s2','C001')); v.reset('s1'); print(v.is_verified('s1','C001'))"
  ```
  Expect: `True False False` then `False`.

### Task 2 — CREATE `src/hooks/normalize.py` (pure `to_iso8601` + TR5 PostToolUse hook)

- **IMPLEMENT**:
  - Pure `to_iso8601(value) -> str`: accept Unix timestamp (`int`/`float` or all-digit string), ISO 8601 (incl. trailing `Z`), and human strings (`"Mar 5, 2025"`). Normalize to canonical `"%Y-%m-%dT%H:%M:%SZ"` (UTC). Unparseable input → return unchanged (never raise — a hook must not break the loop).
  - `normalize_order_dates(input, tool_use_id, context) -> dict`: PostToolUse hook. If `tool_name` endswith `lookup_order`, read the tool result (path per Task 0), and if it has `structuredContent.placedAt`, build a copy with `placedAt` normalized AND replace the date substring in the `content[0].text`. Return `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedMCPToolOutput": <new result>}}`. Otherwise return `{}`.
- **PATTERN**: keep the parse logic pure and separate from the hook so it's tested without the SDK (mirror fixtures' pure-accessor style).
- **IMPORTS**: `from datetime import datetime, timezone`. **No `dateutil`.**
- **GOTCHA**:
  - Python 3.10 `datetime.fromisoformat()` does **not** accept a trailing `"Z"` — replace `"Z"` → `"+00:00"` first.
  - Distinguish `bool` from `int` (`isinstance(True, int)` is `True`) — guard with `and not isinstance(value, bool)`.
  - For the int fixture `1740787200`, use `datetime.fromtimestamp(v, tz=timezone.utc)` → `2025-03-01T00:00:00Z`. For `"Mar 5, 2025"` use `datetime.strptime(s, "%b %d, %Y")` (also try `"%B %d, %Y"`, `"%Y-%m-%d"`) and stamp UTC → `2025-03-05T00:00:00Z`.
  - The model reasons over BOTH `structuredContent.placedAt` and the `content` text — normalize both, or the raw form leaks via the text. Do a string `.replace(old_raw, new_iso)` on the text using the original raw value rendered as the tool did it.
  - Never mutate the original dict in place if `tool_response` is shared — build a deep-ish copy.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); from hooks.normalize import to_iso8601; print(to_iso8601(1740787200)); print(to_iso8601('Mar 5, 2025')); print(to_iso8601('2025-03-15T14:30:00Z')); print(to_iso8601('not a date'))"
  ```
  Expect: `2025-03-01T00:00:00Z` / `2025-03-05T00:00:00Z` / `2025-03-15T14:30:00Z` / `not a date`.

### Task 3 — CREATE `src/hooks/refund_gate.py` (TR3 PreToolUse)

- **IMPLEMENT**: `async def refund_gate(input, tool_use_id, context) -> dict`. If `tool_name` endswith `process_refund` and `float(tool_input.get("amount") or 0) > config.REFUND_POLICY_LIMIT`, return a `permissionDecision: "deny"` with a `permissionDecisionReason` instructing escalation to `escalate_to_human`. Otherwise `{}`.
- **PATTERN**: deny-dict shape from the Verified SDK surface block. Reason = actionable routing instruction (TR3 decision: block is the guarantee, model escalates).
- **IMPORTS**: `import config`.
- **GOTCHA**: Use `> REFUND_POLICY_LIMIT` (strictly over). `== 500.00` is **within** policy → allow. Coerce `amount` safely (`float(... or 0)`); a missing/None amount is not "over limit" — let the tool's own schema handle missing-required (out of scope here). Import the limit from `config`; never hardcode `500`.
- **VALIDATE**:
  ```bash
  $PY -c "
  import asyncio, sys; sys.path.insert(0,'src'); import config; config.load_env()
  from hooks.refund_gate import refund_gate
  def call(a): return asyncio.run(refund_gate({'tool_name':'mcp__support__process_refund','tool_input':{'amount':a,'customer_id':'C002','order_id':'O1002'},'session_id':'s'}, 'tu', {'signal':None}))
  print(call(900).get('hookSpecificOutput',{}).get('permissionDecision'))   # deny
  print(call(500).get('hookSpecificOutput'))                                 # None (allow)
  print(call(42).get('hookSpecificOutput'))                                  # None (allow)
  "
  ```
  Expect: `deny` / `None` / `None`.

### Task 4 — CREATE `src/hooks/prerequisite_gate.py` (TR4 PreToolUse gate + get_customer PostToolUse writer)

- **IMPLEMENT**:
  - `record_verified_customer(input, tool_use_id, context)`: PostToolUse hook. If `tool_name` endswith `get_customer`, extract `structuredContent` from the result (path per Task 0), and **only if `matchCount == 1`**, call `verified_store.mark_verified(input["session_id"], matches[0]["id"])`. Always return `{}` (this hook never blocks/rewrites).
  - `prerequisite_gate(input, tool_use_id, context)`: PreToolUse hook. If `tool_name` endswith `lookup_order` or `process_refund`, read `tool_input.get("customer_id")` and `input.get("session_id","")`; if the id is missing or `not verified_store.is_verified(session_id, customer_id)`, return `permissionDecision: "deny"` with a reason telling the model to call `get_customer` and obtain a single verified match first. Otherwise `{}`.
  - Add a small `_extract_structured(tool_response) -> dict | None` helper documenting the observed shape from Task 0.
- **PATTERN**: defensive `.endswith` tool-name checks; deny-dict shape as above.
- **IMPORTS**: `from hooks import verified_store`.
- **GOTCHA**:
  - **`matchCount > 1` must NOT verify** — that's the whole TR7 duplicate-name path (`get_customer(name="John Smith")` → 2 matches → agent must ask, gate stays closed). Only `== 1` marks verified.
  - The writer depends on the `tool_response` shape from Task 0 — if `structuredContent` isn't directly accessible, parse the JSON out of `content[0].text` or whatever Task 0 revealed, and comment the path.
  - Hook **ordering**: for `process_refund` both `prerequisite_gate` and `refund_gate` match. Either deny is sufficient; both running is fine. An unverified over-limit refund may be denied by whichever fires first — acceptable.
- **VALIDATE**:
  ```bash
  $PY -c "
  import asyncio, sys; sys.path.insert(0,'src')
  from hooks import verified_store as v
  from hooks.prerequisite_gate import prerequisite_gate
  def gate(cid, sid='s'): return asyncio.run(prerequisite_gate({'tool_name':'mcp__support__lookup_order','tool_input':{'customer_id':cid,'order_id':'O1001'},'session_id':sid},'tu',{'signal':None}))
  print(gate('C001').get('hookSpecificOutput',{}).get('permissionDecision'))  # deny (not verified)
  v.mark_verified('s','C001')
  print(gate('C001').get('hookSpecificOutput'))                                # None (allow)
  print(gate('C002').get('hookSpecificOutput',{}).get('permissionDecision'))   # deny (different id)
  "
  ```
  Expect: `deny` / `None` / `deny`.

### Task 5 — UPDATE `src/agent.py` (wire hooks into `build_options`)

- **IMPLEMENT**: Add `from claude_agent_sdk import ClaudeAgentOptions, HookMatcher`. Add a `_build_hooks()` returning:
  ```python
  {
    "PreToolUse": [
      HookMatcher(matcher="mcp__support__lookup_order|mcp__support__process_refund", hooks=[prerequisite_gate]),
      HookMatcher(matcher="mcp__support__process_refund", hooks=[refund_gate]),
    ],
    "PostToolUse": [
      HookMatcher(matcher="mcp__support__get_customer", hooks=[record_verified_customer]),
      HookMatcher(matcher="mcp__support__lookup_order", hooks=[normalize_order_dates]),
    ],
  }
  ```
  Pass `hooks=_build_hooks()` into the existing `ClaudeAgentOptions(...)`. Import the four hook callables from `src/hooks/`.
- **PATTERN**: keep the existing options EXACTLY (`model`, `system_prompt`, `tools=[]`, `mcp_servers`, `allowed_tools`, `strict_mcp_config=True`, `max_turns`). **Do not edit `SYSTEM_PROMPT`.**
- **IMPORTS**: `from hooks.refund_gate import refund_gate`; `from hooks.prerequisite_gate import prerequisite_gate, record_verified_customer`; `from hooks.normalize import normalize_order_dates`.
- **GOTCHA**:
  - **matcher semantics are not guaranteed to be full regex.** The internal `.endswith()` checks (Tasks 3/4/2) make correctness independent of matcher matching — even `matcher=None` would be safe. If Task 0 showed the alternation `A|B` matcher does NOT fire for both tools, fall back to two separate `HookMatcher`s for the prerequisite gate (one per tool) — the defensive internal checks mean over-broad matching is harmless either way.
  - Preserving `tools=[]` keeps the registry small so the CLI does not defer tools behind `ToolSearch` (Phase 1 note 5) — do not drop it.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); import config; config.load_env(); from agent import build_options; o=build_options(); print(sorted(o.hooks.keys())); print('tools', o.tools, 'strict', o.strict_mcp_config)"
  ```
  Expect: `['PostToolUse', 'PreToolUse']` and `tools [] strict True`.

### Task 6 — CREATE `tests/test_hooks_refund_gate.py` (deterministic, no API)

- **IMPLEMENT**: Parameterize ≥20 amounts: a spread above the limit (500.01, 501, 750, 900, 1000, 5000, 999999, …) all asserting `permissionDecision == "deny"`; and a spread at/under (0, 1, 42, 250, 499.99, 500.00) all asserting allow (`{}` / no `hookSpecificOutput`). This is the **TR3 100%-redirect proof across 20+ cases** — deterministic, no model. Also assert the deny reason mentions escalation.
- **PATTERN**: `@pytest.mark.parametrize`; call `asyncio.run(refund_gate(...))` (or make tests `async` with the asyncio marker like Phase 1). No `integration` marker — these never hit the API.
- **IMPORTS**: `import config`, `from hooks.refund_gate import refund_gate`.
- **GOTCHA**: Drive the limit from `config.REFUND_POLICY_LIMIT` in the test too, so changing the policy reparameterizes the boundary instead of breaking hardcoded assertions.
- **VALIDATE**: `$PY -m pytest tests/test_hooks_refund_gate.py -v`

### Task 7 — CREATE `tests/test_hooks_prerequisite_gate.py` (deterministic, no API)

- **IMPLEMENT**: With an autouse `verified_store.reset()` fixture:
  - `process_refund`/`lookup_order` with an unverified `customer_id` → deny (**TR4: process_refund provably impossible before verification**).
  - After `record_verified_customer` processes a synthetic single-match `get_customer` result (matchCount==1) → same call now allowed.
  - A synthetic **multi-match** `get_customer` result (matchCount==2) → still denied (never verifies).
  - Session isolation: verifying in `s1` does not allow the same id in `s2`.
  - `get_customer` itself is never gated (no customer_id requirement).
- **PATTERN**: build synthetic PostToolUse `input` dicts whose `tool_response` matches the Task-0 shape; assert via `verified_store.is_verified`.
- **IMPORTS**: `from hooks import verified_store`; `from hooks.prerequisite_gate import prerequisite_gate, record_verified_customer`.
- **GOTCHA**: Use the EXACT `tool_response` shape observed in Task 0 (don't hand-wave the structuredContent path). Reset the store between tests or sessions leak.
- **VALIDATE**: `$PY -m pytest tests/test_hooks_prerequisite_gate.py -v`

### Task 8 — CREATE `tests/test_hooks_normalize.py` (deterministic, no API)

- **IMPLEMENT**: Unit-test `to_iso8601` for all three fixture formats + an unparseable passthrough (and a `bool` guard case). Then test `normalize_order_dates` end-to-end on a synthetic `lookup_order` `tool_response` (built from `fixtures.ORDERS["O1001"]` shape): assert the returned `updatedMCPToolOutput` has `structuredContent.placedAt == "2025-03-01T00:00:00Z"` AND the `content[0].text` no longer contains the raw `1740787200`.
- **PATTERN**: mirror `tests/test_fixtures.py` (pure, fast, no marker).
- **IMPORTS**: `from hooks.normalize import to_iso8601, normalize_order_dates`; `from mocks import fixtures`.
- **GOTCHA**: Construct the synthetic `tool_response` to match Task 0's observed shape, not the idealized `_result()` dict, if they differ.
- **VALIDATE**: `$PY -m pytest tests/test_hooks_normalize.py -v`

### Task 9 — CREATE `tests/test_phase2_guardrails_live.py` (few live integration tests)

- **IMPLEMENT**: `pytestmark` = integration + skipif (mirror `test_phase1_order_status.py:19-22`). Tests:
  1. **Over-limit refund → blocked, escalates.** Prompt: Bob Martinez (bob@example.com) asks for a full refund on his $900 order O1002. Assert: `process_refund` is **either never called or its over-limit call did not succeed**, and `escalate_to_human` appears in `tool_calls`. (Behavior assertion: block is guaranteed deterministically by Task 6; here we confirm the model escalates in response.)
  2. **Verified-then-lookup still works (no regression).** Reuse the Phase 1 Alice/O1001 prompt; assert `get_customer` before `lookup_order`, `subtype == "success"`.
  3. **ISO date surfaced (TR5).** Alice asks for status of O1001 (Unix-timestamp date); assert the final answer contains `2025-03-01` (the normalized date), not a raw epoch. Keep it a lenient substring check.
  4. *(optional)* **In-policy refund proceeds.** A small (<$500) refund on a verified order is not blocked by the refund gate.
- **PATTERN**: assert on `run.tool_calls` membership/order and `run.subtype` — never on phrasing (one lenient date substring is the only prose touch). Use the `run_agent` fixture.
- **IMPORTS**: `import config`, `import shutil`, the `run_agent` fixture from conftest.
- **GOTCHA**: Live + model-driven → keep assertions on tool membership and the deterministic outcome, not exact counts/wording. The hard guarantee is already proven in Task 6; these guard the end-to-end calibration. If the model occasionally fails to escalate after a block, that's a system-prompt/reason-wording signal (improve the deny reason or escalation guidance) — not a reason to delete the assertion.
- **VALIDATE**: `$PY -m pytest tests/test_phase2_guardrails_live.py -v`

### Task 10 — UPDATE `tests/conftest.py` (verified-store reset fixture) + full regression

- **IMPLEMENT**: Add an `autouse` fixture that calls `verified_store.reset()` before each test so the process-global store never leaks across cases. Confirm import path works (`from hooks import verified_store`). Then run the FULL suite and confirm no Phase 1 regressions.
- **GOTCHA**: The autouse reset must be importable without the API (no SDK import in `verified_store`). Place the import inside the fixture or at module top after the `sys.path` insert.
- **VALIDATE**:
  ```bash
  cd /Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/customer-support && \
  $PY -m pytest tests/ -v            # all green: phase1 + phase2 deterministic + (live if claude CLI present)
  $PY -m pytest tests/ -v -m "not integration"   # deterministic-only subset must pass with zero API calls
  ```

---

## TESTING STRATEGY

Framework: **pytest** + `pytest-asyncio` (already configured). Ground truth = tool calls + outcomes, not prose. Per the locked decision, the deterministic guarantees are proven **without the model**; live tests confirm end-to-end calibration.

### Unit Tests (no API key / no CLI needed — the bulk of the proof)
- **Refund gate (TR3):** ≥20 parameterized amounts; 100% of `> limit` deny, all `<= limit` allow; boundary at `config.REFUND_POLICY_LIMIT`.
- **Prerequisite gate (TR4):** deny before verification; allow after a single-match `get_customer`; multi-match never verifies; session isolation; `get_customer` itself ungated.
- **Normalization (TR5):** `to_iso8601` across Unix int / human string / ISO / unparseable / bool guard; hook rewrites both `structuredContent.placedAt` and the `content` text.
- **verified_store:** mark/is/reset, session keying.

### Integration Tests (live; gated on `shutil.which("claude")`)
- Over-limit refund → blocked + escalates; verified-then-lookup happy path (regression); ISO date in the answer; (optional) in-policy refund proceeds.

### Edge Cases
- Refund exactly at the limit (`== 500.00`) → allowed.
- Over-limit AND unverified → denied (either gate); confirm no double-execution.
- `get_customer` returns 0 matches → not verified → subsequent lookup denied.
- Duplicate-name `get_customer` (2 matches) → not verified → gate stays closed (TR7 path preserved).
- Unparseable `placed_at` → normalizer returns it unchanged, never raises (loop must not break).
- Two issues in one message that each require verification (smoke only; full multi-issue is Phase 4).

---

## VALIDATION COMMANDS

`$PY = /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python`. Run from `projects/customer-support/`.

### Level 1: Syntax & Style
```bash
$PY -m py_compile src/agent.py src/hooks/__init__.py src/hooks/verified_store.py src/hooks/normalize.py src/hooks/refund_gate.py src/hooks/prerequisite_gate.py
# Optional if installed: ruff check src tests && black --check src tests
```

### Level 2: Unit Tests (deterministic — zero API calls)
```bash
$PY -m pytest tests/ -v -m "not integration"
```

### Level 3: Integration Tests (requires the `claude` CLI / live API)
```bash
$PY -m pytest tests/test_phase2_guardrails_live.py -v
```

### Level 4: Manual Validation
```bash
# Over-limit refund is blocked and routed to escalation:
$PY -c "
import asyncio, sys; sys.path.insert(0,'src'); import config; config.load_env()
from loop import run_turn; from agent import build_options
run = asyncio.run(run_turn('Hi, I am Bob Martinez (bob@example.com). Please refund my entire \$900 order O1002.', build_options()))
print('TOOLS:', run.tool_calls)            # expect escalate_to_human; process_refund (if attempted) was denied
print('SUBTYPE:', run.subtype); print('TEXT:', run.final_text[:300])
"
# ISO date normalization surfaces in the answer:
$PY -c "
import asyncio, sys; sys.path.insert(0,'src'); import config; config.load_env()
from loop import run_turn; from agent import build_options
run = asyncio.run(run_turn('I am Alice Wong, alice@example.com. Status of order O1001?', build_options()))
print('2025-03-01' in run.final_text, run.final_text[:200])
"
```

### Level 5: Additional Validation (Optional)
- Re-run `tests/test_phase2_guardrails_live.py` 3× to gauge escalation-calibration stability (tool membership should be stable; wording varies).
- After completing, append an **EXECUTION NOTES** section to this plan recording the real `tool_response` shape (Task 0) and any matcher-semantics findings, for Phase 3.

---

## ACCEPTANCE CRITERIA

- [ ] **TR3:** 100% of over-limit (`> $500`) `process_refund` attempts are denied by the PreToolUse hook — proven across ≥20 deterministic cases; the limit is read from `config.REFUND_POLICY_LIMIT` (no hardcode); no prompt instruction added.
- [ ] **TR3 calibration (live):** an over-limit refund request results in `escalate_to_human` and never a successful refund.
- [ ] **TR4:** `lookup_order`/`process_refund` are provably impossible before a single-match `get_customer`; multi-match never verifies; verified state is session-isolated — all proven deterministically.
- [ ] **TR5:** `lookup_order` output reaches the model with `placed_at`/`placedAt` in canonical ISO 8601 (both structured field and human text); Unix/human/ISO inputs all normalize; unparseable input passes through without raising.
- [ ] Hooks are wired in `build_options()`; Phase 1 options (`tools=[]`, `strict_mcp_config=True`, `allowed_tools`, `SYSTEM_PROMPT`) are unchanged.
- [ ] System prompt contains **no** refund-limit / always-verify / date-format instruction (deterministic-vs-probabilistic thesis upheld).
- [ ] `pytest tests/ -m "not integration"` passes with zero API calls; full suite green; **no Phase 1 regressions**.
- [ ] No new third-party dependencies (stdlib `datetime` only).

---

## COMPLETION CHECKLIST

- [ ] Task 0 confirmed hooks fire and the real `tool_response` shape is recorded in code comments.
- [ ] All tasks completed in order; each task's VALIDATE passed before moving on.
- [ ] Level 1–3 validation commands pass; Level 4 manual checks show block→escalate and ISO date.
- [ ] Deterministic suite proves TR3 (≥20 cases) and TR4 (gate) without the model.
- [ ] `build_options()` unchanged except for the added `hooks=`.
- [ ] Acceptance criteria all met; EXECUTION NOTES appended for Phase 3.

---

## NOTES

**Locked design decisions (confirmed with the user before planning):**
1. **TR3 semantics — block is the guarantee; model escalates.** The PreToolUse deny (refund never executes) is the deterministic, 100%-provable invariant, tested on ≥20 synthetic amounts with no model. The agent's `escalate_to_human` follow-through is its calibrated response, verified leniently via a live test. We do NOT make a "deterministic" acceptance hinge on model behavior.
2. **Test strategy — deterministic hook unit tests + a few live.** The 20+ over-limit cases and the prerequisite proof are unit tests against the hook callables (fast, free, truly 100%). A small live suite guards end-to-end calibration. (Phase 1 was live-only; this is the deliberate shift.)
3. **Scope — exactly TR3/TR4/TR5.** No order existence/ownership validation added to `process_refund` (not spec-required; deferred). No touching of the system prompt, tools, loop, or fixtures' shape.

**Design rationale & trade-offs:**
- **Verified state via a PostToolUse hook on `get_customer` + a session-keyed store**, rather than inside the tool: the tool only sees `args` (no `session_id`), so a tool-internal store would be process-global and leak across runs/tests. The hook has `session_id` from `BaseHookInput`, giving clean per-run isolation. The PreToolUse prerequisite gate reads the same store.
- **`updatedMCPToolOutput` (rewrite) over `additionalContext` (append) for TR5:** the spec says normalize "before the model reasons over them." Rewriting the output means the model never sees the raw heterogeneous form; appending would leave the raw value visible alongside a note. Rewrite is the faithful reading.
- **Defensive `.endswith()` tool-name checks inside every hook** make correctness independent of `HookMatcher` regex/alternation semantics (which the SDK docstring leaves slightly ambiguous). Matchers become an optimization, not a correctness dependency — so a matcher surprise in Task 0 can't silently disable a guardrail.
- **Pure `to_iso8601` separated from the hook** keeps the date logic SDK-free and exhaustively unit-testable; stdlib-only (no `dateutil`) avoids a new dependency for three known formats.

**Key risks / verify first:**
1. **Exact `tool_response` shape for MCP tools (Task 0).** The PostToolUse `tool_response` may not be the bare `{"content","structuredContent","is_error"}` dict — the MCP layer may wrap it. Tasks 4/5 depend on the real path; Task 0 exists to capture it before writing the writer/normalizer. **This is the single biggest one-pass risk.**
2. **`HookMatcher` matcher semantics for `A|B` alternation** — mitigated by internal `.endswith()` checks and a documented fallback to per-tool matchers.
3. **Live escalation calibration** — the block is guaranteed; whether the model then escalates is model behavior. If flaky, strengthen the deny `permissionDecisionReason` wording (it's the routing signal), not the assertion.

**Confidence (one-pass success): 8/10.** The SDK hooks surface is introspected and recorded (the chief Phase-1 unknown is now closed), the guarantees are proven by deterministic unit tests independent of the model, fixtures already stage every case, and the defensive design tolerates matcher/shape surprises. The one open unknown is the runtime `tool_response` shape (Task 0 de-risks it in minutes); everything downstream of it is mechanical.

---

## EXECUTION NOTES (Phase 2 complete — read before Phase 3)

**Status: DONE.** All tasks executed; 49/49 tests pass (41 deterministic + 4 Phase 1 live + 4 Phase 2 live). No Phase 1 regressions. No new dependencies. System prompt untouched. Phase 1 options (`tools=[]`, `strict_mcp_config=True`, `allowed_tools`, `SYSTEM_PROMPT`) preserved.

### The big Task-0 finding (this changed Tasks 2, 4, 5 — Phase 3 MUST account for it)

The PostToolUse hook's `tool_response` is **the bare content list** — `[{"type": "text", "text": "..."}]` — **NOT** the tool's `{"content", "structuredContent", "is_error"}` dict. `structuredContent` and `is_error` are **dropped by the SDK before any hook (or the model) sees them.**

- **Root cause (verified in source, not guessed):** `claude_agent_sdk/_internal/query.py:645-693` builds the tool result as `response_data = {"content": content}` purely from `result.root.content` (text/image/resource items), plus `isError` only when truthy. It **never reads `structuredContent`**. The CLI then hands the hook `tool_response` as the bare list.
- **Implication for Phase 3 (TR6 structured errors):** the `errorCategory` / `isRetryable` / message struct you plan to return from tools will **NOT reach a PostToolUse/PostToolUseFailure hook via `structuredContent`.** It must travel either (a) inside the `content` text (parse it back out), or (b) be detected by the agent from the text + the `isError` flag. Do not design Phase 3 error handling assuming hooks can read a structured error object off the tool result — they can't. Verify the `PostToolUseFailure` payload shape with a Task-0-style smoke test first.

### `updatedMCPToolOutput` shape (TR5 rewrite — also bare list)

`updatedMCPToolOutput` must be the **bare content list** `[{"type":"text","text": ...}]`, the same shape as `tool_response`. Returning the wrapped `{"content": [...]}` form makes the model see a **tool failure** (empirically confirmed: model reported "the tool is failing"). Both directions use the bare list.

### Adaptations made vs. the original plan (all forced by the Task-0 shape)

- **TR5 (`normalize.py`):** normalizes the date **in the text content** (anchored on the tool's trailing `"placed <value>."` segment), not in `structuredContent` (which doesn't reach the hook/model). This is the faithful reading of "normalize before the model reasons over them" since the text is the *only* surface the model sees. `to_iso8601` stays pure/stdlib (handles Unix int, all-digit string, ISO+Z via `Z`→`+00:00`, human strings; bool-guarded; unparseable → passthrough, never raises).
- **TR4 writer (`prerequisite_gate.record_verified_customer`):** recovers the single-match customer id from `get_customer`'s text via the sentinel regex `Verified customer .*\(id (C###)\)`. That sentence is emitted **only** on a single match; multi-match ("Found N customers …") and zero-match ("No customer found …") don't contain `(id …)`, so they never verify — the TR7 disambiguation path is preserved without reading `matchCount`.
- **Live test `test_iso_date_surfaced_in_answer`:** the model **humanizes** the normalized ISO date in prose (e.g. "March 1, 2025"), so the assertion is format-lenient (accepts ISO or humanized) and the hard signal is **the raw epoch never leaks**. The exact ISO rewrite is proven deterministically in `test_hooks_normalize.py`.

### Matcher semantics (confirmed)

- Fully-qualified matchers (`mcp__support__get_customer`) fire correctly for in-process MCP tools. `matcher=None` matches all tools. The alternation matcher `mcp__support__lookup_order|mcp__support__process_refund` was used for the prerequisite gate and works — but every hook ALSO re-checks the tool name via `.endswith(...)`, so matcher behavior is an optimization, not a correctness dependency. The planned per-tool fallback was not needed.

### Files delivered

- New: `src/hooks/{__init__,verified_store,normalize,refund_gate,prerequisite_gate}.py`
- Updated: `src/agent.py` (`_build_hooks()` + `hooks=` wiring), `tests/conftest.py` (autouse `verified_store.reset()`)
- New tests: `tests/test_hooks_{refund_gate,prerequisite_gate,normalize}.py` (deterministic) + `tests/test_phase2_guardrails_live.py` (live)
