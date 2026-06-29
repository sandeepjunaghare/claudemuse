# Feature: Customer Support Resolution Agent — Phase 3 (Errors + Escalation)

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing. **Pay special attention to the Phase 2 Task-0 finding** (the SDK drops `structuredContent`/`isError` from what hooks and the model see — only the **content text** + a bare `isError` flag survive) and to **preserving all Phase 1/2 invariants** (`tools=[]`, `strict_mcp_config=True`, `allowed_tools`, the deterministic TR3/TR4/TR5 hooks, and the SYSTEM_PROMPT's *behavior-only* discipline for those three).

## Feature Description

Add the three Phase 3 deliverables that make the agent robust under failure and calibrated at the human boundary:

- **TR6 — Structured errors:** every tool returns a structured error envelope `{isError, errorCategory ∈ {transient|validation|business|permission}, isRetryable, message}` when it fails. The agent **retries** `transient` errors, **explains** `business` errors, and **never blindly retries** non-retryable (`validation`/`permission`) ones. The seeded **flaky 503 endpoint** (currently inert) is turned on to exercise transient retry.
- **TR7 — Escalation calibration:** explicit escalation criteria + **2–4 few-shot examples** added to the system prompt — immediate escalate on explicit human request; *acknowledge→resolve→escalate-on-reiteration* for venting; escalate on policy gaps. (Multi-match → ask-for-identifier is already in place from Phase 2 and stays.)
- **TR8 — Structured handoff:** on escalation, `escalate_to_human` emits a **self-contained JSON summary** (customer, order, root_cause, actions_taken, recommended_action, reason_for_escalation). The **model fills** the enriched tool schema; **code deterministically validates** completeness before the handoff is accepted.

The loop (TR1), the four-tool surface (TR2), the mock fixtures, and the deterministic guardrails (TR3/TR4/TR5) are unchanged in shape. TR6/TR8 attach *around* the existing tools and loop; TR7 is the **one deliberate, scoped edit to the system prompt** (escalation few-shots — behavior guidance, which is legitimately probabilistic).

## User Story

As **the retail business, the customer, and the human escalation target**
I want **transient backend blips retried automatically, business/validation/permission failures explained rather than blindly retried, frustrated customers acknowledged before being bounced to a human, and every escalation carrying a complete self-contained handoff**
So that **the agent recovers from flaky infrastructure without giving up, never loops on an unrecoverable error, escalates with calibration instead of reflex, and hands a human everything they need to resolve the case without ever seeing the transcript.**

## Problem Statement

After Phase 2 the tools always return `is_error=False` — there is no error taxonomy, so the agent cannot distinguish a retryable 503 from an unrecoverable "order not found", and the flaky endpoint is disabled (`FLAKY_503_ENABLED = False`) so transient handling is untested. Escalation guidance in the prompt is thin (no few-shots, no venting calibration), risking both over-escalation (bouncing first-time venters) and under-escalation (missing explicit human requests / policy gaps). And `escalate_to_human` emits only a stub acknowledgement — a human receiving it would have **no** structured case context, violating TR8 ("the human can't see the transcript"). These are exactly the failure-handling and handoff competencies (CCA-F D2.2, D5.2, D1.4) Phase 3 must close, proven by a deterministic suite plus a few live calibration tests.

## Solution Statement

- **TR6:** add `src/errors.py` — a small set of envelope builders (`transient_error`, `validation_error`, `business_error`, `permission_error`) that serialize the `{errorCategory, isRetryable, message}` envelope **into the content text** (the only model-visible surface) and set `is_error=True`. Reclassify the tools' existing soft-failures into categories (unknown order → `validation`; owner mismatch → `permission`; non-refundable order → `business`) and add the **transient 503** path to `lookup_order`. Retry is **model-driven** — taught in the system prompt + few-shots, bounded by the existing `max_turns` backstop — not a hook (retry is behavior, not a 100%-invariant). The flaky endpoint gets a **deterministic test seam** so unit tests force a transient-then-success sequence while live runs stay ~10% probabilistic.
- **TR7:** extend `SYSTEM_PROMPT` with explicit escalation criteria + 2–4 few-shots covering the four `reason_for_escalation` values (`explicit_request`, `policy_gap`, `over_limit_refund`, `stalled`) and the venting acknowledge-first principle. **Multi-turn venting reiteration is deferred to Phase 4** (per the locked decision); Phase 3 validates the single-turn signals (a lone venting message does not escalate; an explicit human request does).
- **TR8:** enrich `escalate_to_human`'s input schema with the full handoff structure (typed fields + the `reason_for_escalation` enum); `src/handoff.py` holds the pure validation + assembly logic; a new **PreToolUse hook `handoff_gate`** deterministically validates required-field completeness + enum validity before the tool runs (deny → the model retries with complete data — same mechanism as TR3/TR4). The tool emits the self-contained handoff JSON in its content text. Optional best-effort: stamp `customer.verified` from the Phase 2 `verified_store` via `updatedInput` (gated on Task 0 confirming that works for MCP tools; fall back to model-provided `verified`).

Validation mirrors Phase 2's split: **deterministic unit tests** (tool error categories via the seam, envelope builders, handoff completeness gate) prove the guarantees without the model; **a few live tests** confirm end-to-end calibration (transient recovered, business explained, explicit request escalates, handoff JSON self-contained).

## Feature Metadata

**Feature Type**: Enhancement (adds failure-handling + handoff layers to the Phase 1/2 foundation)
**Estimated Complexity**: Medium
**Primary Systems Affected**: `src/errors.py` (new), `src/handoff.py` (new), `src/hooks/handoff_gate.py` (new), `src/tools/server.py` (error envelopes + escalate schema), `src/mocks/fixtures.py` (flaky seam + business fixture), `src/agent.py` (TR7 few-shots + wire handoff_gate), `tests/` (new deterministic + live suites)
**Dependencies**: No new packages. Uses `claude-agent-sdk` 0.2.110 (installed) and Python stdlib (`json`, `random`) only.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `CLAUDE.md` (project root) — the deterministic-vs-probabilistic thesis. Note its TR6/TR7/TR8 guidance: structured errors with categories + retryability; escalation calibration with few-shots; self-contained handoff JSON. Re-read before touching anything.
- `.agents/plans/customer-support-phase-2.md` (**EXECUTION NOTES**, lines 466–496) — **the load-bearing Task-0 finding**: PostToolUse `tool_response` is the **bare content list** `[{"type":"text","text":...}]`; `structuredContent` and `is_error` are dropped by the SDK before any hook/model sees them. Explicitly warns: *"the errorCategory / isRetryable / message struct you plan to return from tools will NOT reach a hook via structuredContent. It must travel inside the content text."* This drives the entire TR6 design.
- `docs/02-customer-support-prd.md` §10 (lines 192–228) — the **exact contracts**: the TR6 error envelope JSON and the TR8 handoff JSON (with the `reason_for_escalation` enum). Match these field names.
- `docs/01-customer-support-resolution-agent.md` (TR6/TR7/TR8, lines 55–64; acceptance criteria, lines 88–95) — source of truth.
- `src/tools/server.py` — all four tools. `_result()` (lines 28–34) is the return shape to extend; `lookup_order` (115–145) is where the unknown-order/owner-mismatch soft-failures live (reclassify them) and where the transient 503 check goes; `process_refund` (171–180) is the Phase 1 stub to give a `business` error path; `escalate_to_human` (183–211) is the schema to enrich for TR8. **Confirmed:** the `@tool` decorator returns an `SdkMcpTool` exposing `.handler` (the raw async fn) — unit tests call `lookup_order.handler({...})` directly, no refactor needed.
- `src/mocks/fixtures.py` — `FLAKY_503_ENABLED = False` (line 35) flips to `True`; `maybe_fail_transient()` (71–74) is the no-op stub to replace with the deterministic seam. `ORDERS` (24–31): O1002 ($900, C002) is the over-limit case; consider adding one **non-refundable** order for the `business` error.
- `src/agent.py` — `SYSTEM_PROMPT` (26–47) gets the TR7 escalation few-shots **and** a short TR6 error-handling guidance block (the ONLY prompt edits; do NOT add refund-limit/always-verify/date rules — those stay code-only). `_build_hooks()` (50–74) gets the `handoff_gate` PreToolUse matcher.
- `src/config.py` — add Phase 3 constants here (flaky probability, max transient retries hint) so tests/prompt read one source of truth.
- `src/hooks/refund_gate.py` + `src/hooks/prerequisite_gate.py` — the **deny-dict hook shape** and defensive `.endswith()` pattern to mirror in `handoff_gate`.
- `tests/conftest.py` — `_reset_verified_store` autouse fixture (25–35) and `agent_runnable()`/`run_agent` (37–57). Add an autouse reset for the flaky seam here; mirror for new suites.
- `tests/test_phase2_guardrails_live.py` — the live-test `pytestmark` skip pattern + assert-on-`tool_calls`/`subtype` style. Mirror exactly.
- `tests/test_hooks_refund_gate.py` / `test_hooks_normalize.py` — the no-API deterministic unit-test style (parametrize + `asyncio.run(hook(...))`). Mirror for the new deterministic suites.
- `pytest.ini` — `asyncio_mode = auto`; the `integration` marker is registered. No changes needed.

### New Files to Create

- `src/errors.py` — structured error envelope (TR6). Category constants + builders that return the standard tool dict with the envelope **serialized into the content text** and `is_error=True`. Pure, SDK-free, unit-testable.
- `src/handoff.py` — handoff schema/assembly (TR8). Pure: `REQUIRED_FIELDS`, `REASON_VALUES`, `missing_fields(tool_input) -> list[str]`, `build_summary(tool_input) -> dict`. SDK-free.
- `src/hooks/handoff_gate.py` — PreToolUse hook on `escalate_to_human`: deny if required fields missing or `reason_for_escalation` not in enum; optional verified-stamp via `updatedInput` (Task 0 gating).
- `tests/test_errors.py` — deterministic: each builder sets the right category/retryability and serializes a model-legible category tag into the text.
- `tests/test_tools_errors.py` — deterministic (no API, via `.handler` + the flaky seam): `lookup_order` transient/validation/permission; `process_refund` business; success paths unchanged.
- `tests/test_hooks_handoff_gate.py` — deterministic: complete input allowed; each missing required field / bad enum denied with an actionable reason.
- `tests/test_handoff.py` — deterministic: `missing_fields` + `build_summary` produce the PRD §10 shape.
- `tests/test_phase3_errors_escalation_live.py` — a few live tests: transient recovered (seam-forced), business explained, explicit-request escalates immediately, lone-venting does NOT escalate, handoff JSON is self-contained.

### Files to Update

- `src/tools/server.py` — import `errors`; reclassify soft-failures; add transient check to `lookup_order`; add a `business` path to `process_refund`; enrich `escalate_to_human` schema + emit the handoff JSON.
- `src/mocks/fixtures.py` — `FLAKY_503_ENABLED = True`; deterministic seam (`force_transient_failures(n)`, `reset_flaky()`, RNG-based probabilistic mode); optional non-refundable order fixture.
- `src/agent.py` — TR7 few-shots + TR6 guidance in `SYSTEM_PROMPT`; wire `handoff_gate` into `_build_hooks()["PreToolUse"]`.
- `src/config.py` — `FLAKY_503_PROBABILITY = 0.10`, `MAX_TRANSIENT_RETRIES = 3` (a hint surfaced in the prompt; the hard bound stays `MAX_TURNS_BACKSTOP`).
- `tests/conftest.py` — autouse fixture resetting the flaky seam between tests.

### Relevant Documentation — READ THESE BEFORE IMPLEMENTING

- [Claude Agent SDK — Hooks (Python)](https://platform.claude.com/docs/en/agent-sdk/hooks) — PreToolUse `permissionDecision: "deny"` + `permissionDecisionReason` (handoff_gate) and `updatedInput` (optional verified-stamp).
- [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — structured-error design + actionable error messages (TR6); error text should tell the agent what to do next.
- The SDK is the ground truth. **Verified facts** (introspected this phase, do NOT re-guess):
  - `@tool` returns `SdkMcpTool` with `.name`, `.description`, `.input_schema`, `.handler`. `handler` is the original async fn — directly callable in tests.
  - `create_sdk_mcp_server` maps the tool's returned dict to `CallToolResult(content=..., isError=result.get("is_error", False))` (`__init__.py:519`). So **`is_error` (snake_case) is the correct key** and surfaces as MCP `isError`.
  - `query.py:644-695` builds the model-visible tool result from `result.root.content` **only**, adding `isError` *only when truthy*. `structuredContent` is **never read** — confirmed dropped. The envelope MUST live in the content text.

### Patterns to Follow

**Error envelope (serialize into text):** the model reads only the content text + the `isError` flag. Make the category explicit and the message actionable:
```python
# errors.py — text the model reads:
# "<message> [error: category=transient retryable=true]"
```
Keep `structuredContent` populated too (contract fidelity / future-proofing) even though the SDK drops it — the operative surface is the text.

**Hook callback shape (mirror Phase 2):** defensive `.endswith()` tool-name check first; deny via `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "<actionable>"}}`; allow via `{}`.

**Deny/error reason = routing instruction:** phrase every error message and deny reason as an actionable next step ("…this is a transient error; retry the request", "…order not found; ask the customer to confirm the order number", "…handoff is missing root_cause and recommended_action; provide them and call escalate_to_human again").

**Test style:** deterministic tests call `tool.handler(args)` or `hook(input, "tu", {"signal": None})` via `asyncio.run(...)` and assert on the returned dict — no API, no markers. Live tests carry `pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _runnable, ...)]`.

**SYSTEM_PROMPT discipline:** TR7 few-shots + a brief TR6 error-handling paragraph are the ONLY additions. Do **not** encode the refund limit, the always-verify rule, or date formats in the prompt — those are code (TR3/TR4/TR5) and adding them is an automatic failure of the thesis.

---

## IMPLEMENTATION PLAN

### Phase A: Foundation (pure, SDK-free)
`errors.py` (envelope builders) and `handoff.py` (validation + assembly) — both pure and independently unit-testable before any tool/hook wiring. Add Phase 3 config constants.

### Phase B: Tool error taxonomy (TR6)
Turn on the flaky endpoint with a deterministic seam in `fixtures.py`; wire structured errors into the tools (transient/validation/business/permission); confirm success paths are unchanged.

### Phase C: Handoff (TR8)
Enrich `escalate_to_human`'s schema + emit the handoff JSON; add the `handoff_gate` PreToolUse completeness hook; wire it into `build_options()`.

### Phase D: Calibration + guidance (TR7 + TR6 behavior)
Add escalation few-shots and the error-handling guidance to `SYSTEM_PROMPT`. This is where the model is taught category-driven retry and calibrated escalation.

### Phase E: Testing & Validation
Deterministic suites (errors, tool categories via seam, handoff gate, handoff assembly) + a small live suite. Confirm Phase 1/2 suites still pass (no regressions).

---

## STEP-BY-STEP TASKS

Execute in order. `$PY = /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python`. All commands run from the project root `projects/customer-support/`.

### Task 0 — VERIFY the three runtime assumptions (do this FIRST)

- **IMPLEMENT**: Confirm, with quick probes, the facts the rest of Phase 3 depends on:
  1. **`is_error=True` surfaces to the model** as an error result (already source-confirmed at `__init__.py:519`; a live smoke that returns an error from a tool and prints whether the model treats it as an error is optional reassurance).
  2. **`.handler` is directly callable** (already confirmed — `get_customer.handler({'name':'Alice Wong'})` returns the structured dict). Use this for all TR6 tool tests.
  3. **`updatedInput` works for in-process MCP tools** in a PreToolUse hook (needed ONLY for the optional `verified`-stamp in `handoff_gate`). If it does not mutate the tool input, **drop the stamp** and have the model provide `verified` + the tool validate it — the completeness gate (the actual TR8 guarantee) does not depend on it.
- **GOTCHA**: Do not block Phase 3 on (3). The deterministic TR8 guarantee is the **completeness deny**, which uses the same `permissionDecision: "deny"` mechanism already proven in Phase 2. Record the `updatedInput` finding in a comment in `handoff_gate.py`.
- **VALIDATE**: a throwaway smoke driver (mirror Phase 2 Task 0) that (a) registers a PreToolUse hook returning `{"hookSpecificOutput": {"hookEventName":"PreToolUse","updatedInput": {...}}}` for `escalate_to_human` and (b) prints what `tool_input` the tool ultimately received. Confirm whether the mutation took.

### Task 1 — CREATE `src/errors.py` (TR6 envelope) + config constants

- **IMPLEMENT**:
  - Category constants: `TRANSIENT = "transient"`, `VALIDATION = "validation"`, `BUSINESS = "business"`, `PERMISSION = "permission"`.
  - `error_result(message: str, category: str, is_retryable: bool) -> dict` returning the standard tool shape:
    ```python
    {
      "content": [{"type": "text", "text": f"{message} [error: category={category} retryable={'true' if is_retryable else 'false'}]"}],
      "structuredContent": {"isError": True, "errorCategory": category, "isRetryable": is_retryable, "message": message},
      "is_error": True,
    }
    ```
  - Convenience builders: `transient_error(msg)` (retryable=True), `validation_error(msg)`, `business_error(msg)`, `permission_error(msg)` (the last three retryable=False).
  - In `src/config.py`: `FLAKY_503_PROBABILITY = 0.10` and `MAX_TRANSIENT_RETRIES = 3`.
- **PATTERN**: pure, SDK-free (mirror `mocks/fixtures.py`). The category tag in the text is the model's only structured signal (Phase 2 Task-0 finding) — keep it terse and consistent so few-shots can reference the exact phrasing.
- **IMPORTS**: stdlib only.
- **GOTCHA**: `is_error` is snake_case (source-confirmed key). `isRetryable` semantics: only `transient` is retryable in this build; `validation`/`business`/`permission` are not.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); from errors import transient_error, business_error
  t=transient_error('Backend timed out (503).'); print(t['is_error'], t['structuredContent']['errorCategory'], 'category=transient' in t['content'][0]['text'])
  b=business_error('Order already refunded.'); print(b['structuredContent']['isRetryable'], 'retryable=false' in b['content'][0]['text'])"
  ```
  Expect: `True transient True` / `False True`.

### Task 2 — CREATE `src/handoff.py` (TR8 pure validation + assembly)

- **IMPLEMENT**:
  - `REASON_VALUES = ("explicit_request", "policy_gap", "over_limit_refund", "stalled")`.
  - `REQUIRED_FIELDS = ("reason_for_escalation", "root_cause", "recommended_action", "actions_taken")` (plus customer/order context — see GOTCHA on how strict to be).
  - `missing_fields(tool_input: dict) -> list[str]`: returns the names of required fields that are absent/empty, and `"reason_for_escalation(invalid)"` if present-but-not-in-enum.
  - `build_summary(tool_input: dict) -> dict`: assembles the PRD §10 shape:
    ```python
    {
      "customer": {"id": ..., "name": ..., "verified": ...},
      "order": {"id": ..., "status": ..., "amount": ...},
      "root_cause": ..., "actions_taken": [...],
      "recommended_action": ..., "reason_for_escalation": ...,
    }
    ```
- **PATTERN**: pure functions, SDK-free (mirror `normalize.to_iso8601`'s pure/testable split from its hook).
- **IMPORTS**: stdlib only.
- **GOTCHA**: Decide field strictness deliberately. `reason_for_escalation`, `root_cause`, `recommended_action` are always required. `actions_taken` may be an **empty list** (an immediate explicit-request escalation legitimately has no prior actions) — require the *field's presence*, not non-emptiness. `customer`/`order` context: require at least `customer.id` (or `customer_id`); `order` is optional for non-order escalations (e.g., a pure policy-gap question). Document these choices in the docstring — they define what "self-contained" means here.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); from handoff import missing_fields
  print(missing_fields({'reason_for_escalation':'explicit_request','root_cause':'x','recommended_action':'y','actions_taken':[],'customer':{'id':'C001'}}))  # []
  print(missing_fields({'reason_for_escalation':'banana','root_cause':'x'}))  # missing recommended_action/actions_taken + reason_for_escalation(invalid)"
  ```
  Expect: `[]` then a list including `recommended_action`, `actions_taken`, and `reason_for_escalation(invalid)`.

### Task 3 — UPDATE `src/mocks/fixtures.py` (turn on flaky endpoint + deterministic seam + business fixture)

- **IMPLEMENT**:
  - `FLAKY_503_ENABLED = True`.
  - Deterministic seam:
    ```python
    import random
    import config
    _forced_failures = 0
    def force_transient_failures(n: int) -> None:  # test seam
        global _forced_failures; _forced_failures = n
    def reset_flaky() -> None:
        global _forced_failures; _forced_failures = 0
    def maybe_fail_transient() -> bool:
        global _forced_failures
        if _forced_failures > 0:
            _forced_failures -= 1; return True
        return FLAKY_503_ENABLED and random.random() < config.FLAKY_503_PROBABILITY
    ```
    (Change `maybe_fail_transient` from returning `None` to returning a **bool** the tool checks.)
  - Add a non-refundable order for the `business` case, e.g. `O1004` (`C001`, status `"cancelled"`, total `60.00`, any `placed_at`) — a refund against a cancelled order is a business error.
- **PATTERN**: SDK-free; the seam is module-global like `verified_store` — tests MUST reset it between cases (Task 10 conftest fixture).
- **IMPORTS**: stdlib `random`; `import config` for the probability.
- **GOTCHA**: `random.random()` is fine in app code (the workflow-script ban on `Math.random()` does not apply here). The **forced** path is what keeps unit tests deterministic; the probabilistic path is only meaningful in live runs. Keep the probabilistic branch *after* the forced branch so `force_transient_failures` is authoritative.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); from mocks import fixtures as f
  f.force_transient_failures(2); print(f.maybe_fail_transient(), f.maybe_fail_transient(), f.maybe_fail_transient())"  # True True <prob>
  ```
  Expect: `True True False` (third reflects ~10% — almost always False).

### Task 4 — UPDATE `src/tools/server.py` (wire TR6 structured errors)

- **IMPLEMENT**:
  - `import errors` and `from mocks import fixtures`.
  - `get_customer`: no identifier provided → `errors.validation_error("No identifier provided. Ask the customer for a name, email, or phone number.")`. (0/1/many matches stay non-error — multi-match is the TR7 ask path, not an error.)
  - `lookup_order`:
    - **First**, `if fixtures.maybe_fail_transient(): return errors.transient_error("The order service is temporarily unavailable (HTTP 503). This is a transient error; retry the request.")`.
    - Unknown order → `errors.validation_error("No order found with id <id>. Ask the customer to confirm their order number.")`.
    - Owner mismatch → `errors.permission_error("Order <id> is not associated with customer <cid>.")`.
    - Found + owned → unchanged success `_result(...)` (TR5 normalization hook still applies downstream).
  - `process_refund`: add a `business` path — if the order is non-refundable (e.g. status `cancelled`) or `amount` exceeds the order total → `errors.business_error(...)` explaining why (the agent explains, does not retry). Keep the success confirmation otherwise. (Lookup the order via `fixtures.get_order` to check status/total. Over-limit is still the TR3 hook's job — do not duplicate the limit here.)
  - `escalate_to_human`: handled in Task 5.
- **PATTERN**: error message = actionable instruction; mirror existing `_result` for success.
- **IMPORTS**: `import errors`, `from mocks import fixtures` (already imported).
- **GOTCHA**:
  - **Ordering in `lookup_order`:** the transient check must come *before* the unknown/mismatch checks so a 503 is reported as transient (retryable), not misclassified.
  - The TR4 prerequisite gate runs *before* the tool, so `lookup_order`/`process_refund` only execute for a verified customer — the transient/business errors here are about the *backend*, not identity.
  - Do not change tool **names, descriptions, or input schemas** for the first three tools (TR2 disambiguation is locked). Only the return values change.
- **VALIDATE**:
  ```bash
  $PY -c "import sys, asyncio; sys.path.insert(0,'src'); import config; config.load_env()
  from tools.server import lookup_order; from mocks import fixtures as f
  f.force_transient_failures(1)
  print(asyncio.run(lookup_order.handler({'customer_id':'C001','order_id':'O1001'}))['structuredContent']['errorCategory'])  # transient
  print(asyncio.run(lookup_order.handler({'customer_id':'C001','order_id':'O9999'}))['structuredContent']['errorCategory'])  # validation
  print(asyncio.run(lookup_order.handler({'customer_id':'C002','order_id':'O1001'}))['structuredContent']['errorCategory'])  # permission"
  ```
  Expect: `transient` / `validation` / `permission`.

### Task 5 — UPDATE `src/tools/server.py` (`escalate_to_human` TR8 schema + handoff emit)

- **IMPLEMENT**: enrich the input schema to the PRD §10 handoff structure:
  - `reason_for_escalation` (string, enum = `handoff.REASON_VALUES`, required), `root_cause` (string, required), `recommended_action` (string, required), `actions_taken` (array of strings, required — may be empty), `customer` (object `{id, name, verified}`) and `order` (object `{id, status, amount}`). Keep a free-text `reason`/summary optional for readability. Update the **description** to instruct the model to populate all fields from what it learned in the conversation.
  - Handler: build the summary via `handoff.build_summary(args)` and return a confirmation whose **content text contains the serialized JSON** (`json.dumps(summary)`) so it is inspectable end-to-end; also place it in `structuredContent`.
- **PATTERN**: rich tool description (TR2 style) telling the model exactly what each field is and that the human cannot see the transcript.
- **IMPORTS**: `import json`, `import handoff`.
- **GOTCHA**: The **deterministic completeness guarantee is the `handoff_gate` hook (Task 6)**, not the tool — by the time the handler runs, the gate has already ensured required fields exist. The handler can assume validity but should still assemble defensively (treat missing optional `order` as omitted, not crash).
- **VALIDATE**:
  ```bash
  $PY -c "import sys, asyncio; sys.path.insert(0,'src')
  from tools.server import escalate_to_human
  out=asyncio.run(escalate_to_human.handler({'reason_for_escalation':'explicit_request','root_cause':'Customer demanded a manager.','recommended_action':'Call back within 1h.','actions_taken':['verified identity'],'customer':{'id':'C001','name':'Alice Wong','verified':True}}))
  print('reason_for_escalation' in out['content'][0]['text'])"
  ```
  Expect: `True`.

### Task 6 — CREATE `src/hooks/handoff_gate.py` (TR8 PreToolUse completeness gate)

- **IMPLEMENT**: `async def handoff_gate(input, tool_use_id, context) -> dict`:
  - Defensive: `if not input.get("tool_name","").endswith("escalate_to_human"): return {}`.
  - `missing = handoff.missing_fields(input.get("tool_input", {}))`.
  - If `missing`: return `permissionDecision: "deny"` with a reason naming the missing/invalid fields and instructing the model to re-call `escalate_to_human` with them filled.
  - Else: `{}` (allow). **Optional** (Task 0 gating): if `updatedInput` works, stamp `customer.verified` from `verified_store.is_verified(session_id, customer_id)` to make the verified flag a code-backed fact rather than a model claim.
- **PATTERN**: mirror `prerequisite_gate`'s deny shape + defensive tool-name check.
- **IMPORTS**: `import handoff`; (optional) `from hooks import verified_store`.
- **GOTCHA**: The gate runs on EVERY `escalate_to_human` call, so an incomplete first attempt is denied with guidance and the model retries — bounded by `max_turns`. Keep the deny reason specific (list the exact missing fields) so the retry succeeds in one hop.
- **VALIDATE**:
  ```bash
  $PY -c "import sys, asyncio; sys.path.insert(0,'src')
  from hooks.handoff_gate import handoff_gate
  bad=asyncio.run(handoff_gate({'tool_name':'mcp__support__escalate_to_human','tool_input':{'reason_for_escalation':'explicit_request'},'session_id':'s'},'tu',{'signal':None}))
  print(bad.get('hookSpecificOutput',{}).get('permissionDecision'))  # deny
  good=asyncio.run(handoff_gate({'tool_name':'mcp__support__escalate_to_human','tool_input':{'reason_for_escalation':'explicit_request','root_cause':'x','recommended_action':'y','actions_taken':[],'customer':{'id':'C001'}},'session_id':'s'},'tu',{'signal':None}))
  print(good.get('hookSpecificOutput'))  # None (allow)"
  ```
  Expect: `deny` / `None`.

### Task 7 — UPDATE `src/agent.py` (wire handoff_gate + TR7 few-shots + TR6 guidance)

- **IMPLEMENT**:
  - Import `from hooks.handoff_gate import handoff_gate`; add to `_build_hooks()["PreToolUse"]`: `HookMatcher(matcher=f"mcp__{config.MCP_SERVER_NAME}__escalate_to_human", hooks=[handoff_gate])`.
  - Extend `SYSTEM_PROMPT` with TWO scoped additions:
    - **Error handling (TR6):** a short paragraph: "If a tool reports a *transient* error (e.g. a 503), retry it — up to a few attempts. If it reports a *business*, *validation*, or *permission* error, do NOT retry; explain the situation to the customer in plain language, or escalate if it blocks resolution."
    - **Escalation calibration (TR7):** explicit criteria + 2–4 few-shots illustrating: (a) explicit human request → escalate immediately (`reason_for_escalation=explicit_request`); (b) first-time venting → acknowledge + attempt resolution, do NOT escalate on the first frustrated message (escalate only if the customer reiterates the demand); (c) policy gap / genuine inability to proceed → escalate (`policy_gap` / `stalled`); (d) over-limit refund (after the deterministic block) → escalate (`over_limit_refund`). Remind it that `escalate_to_human` needs root_cause, recommended_action, actions_taken, and the customer/order context filled in.
- **PATTERN**: behavior-only prompt edits. Few-shots reference the exact `reason_for_escalation` enum values and the error-category words used by `errors.py` so guidance and code share vocabulary.
- **IMPORTS**: `from hooks.handoff_gate import handoff_gate`.
- **GOTCHA**: **Do NOT** add the refund limit, the always-verify rule, or date formats to the prompt — they are TR3/TR4/TR5 code. Adding them is an automatic failure. Keep the existing multi-match ask-for-identifier sentence (TR7 disambiguation) — it stays.
- **VALIDATE**:
  ```bash
  $PY -c "import sys; sys.path.insert(0,'src'); import config; config.load_env(); from agent import build_options, SYSTEM_PROMPT
  o=build_options(); pre=o.hooks['PreToolUse']; print('handoff matcher wired:', any('escalate_to_human' in (m.matcher or '') for m in pre))
  print('no refund-limit leak:', '500' not in SYSTEM_PROMPT and 'always verify' not in SYSTEM_PROMPT.lower())"
  ```
  Expect: `True` / `True`.

### Task 8 — CREATE deterministic test suites (no API)

- **IMPLEMENT**:
  - `tests/test_errors.py`: each builder sets the right `errorCategory`/`isRetryable`/`is_error` and embeds the `category=…`/`retryable=…` tag in the text.
  - `tests/test_tools_errors.py`: via `.handler` + `fixtures.force_transient_failures` — `lookup_order` transient (forced) / validation (unknown order) / permission (owner mismatch) / success (unchanged shape, `is_error` absent or False); `process_refund` business (cancelled order / amount > total) and success; `get_customer` no-identifier → validation, single/multi/zero match unchanged (multi-match is NOT an error).
  - `tests/test_handoff.py`: `missing_fields` (complete → `[]`; each missing field flagged; bad enum flagged) + `build_summary` shape matches PRD §10.
  - `tests/test_hooks_handoff_gate.py`: complete allowed; incomplete/bad-enum denied with the field names in the reason.
- **PATTERN**: parametrize; `asyncio.run(...)`; no `integration` marker; reset the flaky seam per test.
- **IMPORTS**: `from errors import ...`, `from tools.server import lookup_order, process_refund, get_customer`, `from mocks import fixtures`, `from handoff import ...`, `from hooks.handoff_gate import handoff_gate`.
- **GOTCHA**: reset `fixtures.reset_flaky()` between tool tests (autouse fixture, Task 10) or a leftover forced failure bleeds into the next case.
- **VALIDATE**: `$PY -m pytest tests/test_errors.py tests/test_tools_errors.py tests/test_handoff.py tests/test_hooks_handoff_gate.py -v`

### Task 9 — CREATE `tests/test_phase3_errors_escalation_live.py` (few live tests)

- **IMPLEMENT**: `pytestmark` = integration + skipif (mirror Phase 2). Tests:
  1. **Transient retried → resolved.** Force one transient failure (`fixtures.force_transient_failures(1)`) before an Alice/O1001 status query; assert `lookup_order` appears (≥1×), the run still ends `subtype == "success"`, and the raw `"503"` does not dominate the final answer (the customer gets the status, not an error). *(The deterministic proof that the category is `transient` is in Task 8; here we confirm the model retries rather than gives up.)*
  2. **Business error explained, not retried blindly.** A refund on the cancelled order → assert the model does not loop (`terminated_by_cap is False`) and escalates or explains (no successful refund).
  3. **Explicit request escalates immediately.** "Get me a manager." → `escalate_to_human` in `tool_calls`; `terminated_by_cap is False`.
  4. **Lone venting does NOT escalate.** A single frustrated-but-actionable message ("This is the third time my order is late and I'm furious — where is order O1001?") for Alice → assert it resolves the order (`lookup_order` present) and does **not** call `escalate_to_human` on this first turn. *(Reiteration→escalate is a Phase 4 multi-turn test.)*
  5. **Handoff is self-contained.** After an explicit-request escalation, assert the final/handoff text contains the customer id and a `reason_for_escalation` value (lenient substring) — proving the JSON carries standalone context.
- **PATTERN**: assert on `tool_calls` membership/order + `subtype`/`terminated_by_cap`; at most one lenient substring per prose touch. Use `run_agent`.
- **IMPORTS**: `import shutil`, `import config`, `from mocks import fixtures`, the `run_agent` fixture.
- **GOTCHA**: Live + model-driven → keep assertions on tool membership and deterministic outcomes. Test 4 (venting) is the most model-dependent; if it flakes, the lever is the few-shot wording (TR7), not deleting the assertion. The hard guarantees (error categories, handoff completeness) are already proven deterministically in Task 8.
- **VALIDATE**: `$PY -m pytest tests/test_phase3_errors_escalation_live.py -v`

### Task 10 — UPDATE `tests/conftest.py` + full regression

- **IMPLEMENT**: add an autouse fixture resetting the flaky seam (`fixtures.reset_flaky()`) before/after each test, alongside the existing `verified_store.reset()`. Run the FULL suite; confirm no Phase 1/2 regressions.
- **GOTCHA**: import `from mocks import fixtures` is SDK-free and safe without the API. Resetting matters because both `verified_store` and the flaky seam are process-global.
- **VALIDATE**:
  ```bash
  cd /Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/customer-support && \
  $PY -m pytest tests/ -v -m "not integration"   # all deterministic green, zero API calls
  $PY -m pytest tests/ -v                         # full suite incl. live (if claude CLI present)
  ```

---

## TESTING STRATEGY

Framework: **pytest** + `pytest-asyncio` (configured). Ground truth = tool calls + outcomes + structured envelope/handoff fields, never prose. Deterministic guarantees proven without the model; live tests confirm end-to-end calibration.

### Unit Tests (no API — the bulk of the proof)
- **Error envelope (TR6):** every builder sets the correct category/retryability/`is_error` and embeds the model-legible category tag in the text.
- **Tool categories (TR6):** via `.handler` + the deterministic flaky seam — `lookup_order` transient/validation/permission; `process_refund` business; `get_customer` validation; all success paths unchanged. Transient is the only retryable category.
- **Handoff completeness (TR8):** `missing_fields` flags every absent required field + bad enum; `build_summary` matches the PRD §10 shape; `handoff_gate` denies incomplete, allows complete.

### Integration Tests (live; gated on `shutil.which("claude")`)
- Transient retried→resolved (seam-forced); business explained (no blind retry, no cap-termination); explicit request escalates immediately; lone venting does not escalate; handoff JSON self-contained.

### Edge Cases
- Two consecutive forced transient failures then success → model retries through both (live, lenient) / seam returns `True,True,False` (unit).
- `actions_taken: []` on an immediate escalation → allowed (presence, not non-emptiness).
- Multi-match `get_customer` → still NOT an error (TR7 ask path preserved).
- Over-limit refund → still the TR3 deny (unchanged); the resulting escalation now carries a full handoff (`reason_for_escalation=over_limit_refund`).
- Owner mismatch → `permission` (not retried).

---

## VALIDATION COMMANDS

`$PY = /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python`. Run from `projects/customer-support/`.

### Level 1: Syntax & Style
```bash
$PY -m py_compile src/errors.py src/handoff.py src/hooks/handoff_gate.py src/tools/server.py src/mocks/fixtures.py src/agent.py src/config.py
```

### Level 2: Unit Tests (deterministic — zero API calls)
```bash
$PY -m pytest tests/ -v -m "not integration"
```

### Level 3: Integration Tests (requires the `claude` CLI / live API)
```bash
$PY -m pytest tests/test_phase3_errors_escalation_live.py -v
```

### Level 4: Manual Validation
```bash
# Transient retried then resolved:
$PY -c "
import asyncio, sys; sys.path.insert(0,'src'); import config; config.load_env()
from mocks import fixtures as f; f.force_transient_failures(1)
from loop import run_turn; from agent import build_options
run = asyncio.run(run_turn(\"Hi, I'm Alice Wong (alice@example.com). Status of order O1001?\", build_options()))
print('TOOLS:', run.tool_calls); print('SUBTYPE:', run.subtype)  # lookup_order retried; success
"
# Over-limit refund → blocked → escalation carries a full handoff:
$PY -c "
import asyncio, sys; sys.path.insert(0,'src'); import config; config.load_env()
from loop import run_turn; from agent import build_options
run = asyncio.run(run_turn('I am Bob Martinez (bob@example.com). Refund my entire \$900 order O1002.', build_options()))
print('TOOLS:', run.tool_calls); print('reason_for_escalation' in run.final_text or 'escalate_to_human' in run.tool_calls)
"
```

### Level 5: Additional Validation (Optional)
- Re-run the live suite 3× to gauge escalation/retry calibration stability (tool membership should be stable; wording varies).
- After completing, append an **EXECUTION NOTES** section recording the `updatedInput` finding (Task 0) and any error-message wording that improved retry/escalation calibration, for Phase 4.

---

## ACCEPTANCE CRITERIA

- [ ] **TR6 envelope:** all tools return `{is_error, errorCategory, isRetryable, message}` on failure, with the category/retryability serialized into the **content text** (the only model-visible surface — Phase 2 Task-0 finding); `is_error=True` surfaces as MCP `isError`.
- [ ] **TR6 categories:** `lookup_order` produces transient (flaky 503) / validation (unknown order) / permission (owner mismatch); `process_refund` produces business (non-refundable / over-total); only `transient` is retryable — all proven deterministically via `.handler` + the seam.
- [ ] **TR6 behavior (live):** a forced transient is retried and the request resolves; a business error is explained and NOT blindly retried (no cap-termination); non-retryable errors are not retried.
- [ ] **TR7:** escalation few-shots in the system prompt cover explicit request (immediate), first-time venting (acknowledge, no escalate), policy gap, and over-limit refund; multi-match ask-for-identifier preserved. (Multi-turn venting-reiteration deferred to Phase 4 by decision.)
- [ ] **TR8:** `escalate_to_human` emits a self-contained handoff JSON (PRD §10 shape); the `handoff_gate` PreToolUse hook deterministically denies incomplete/invalid-enum handoffs so the model retries with complete data.
- [ ] System prompt contains **no** refund-limit / always-verify / date-format instruction (deterministic-vs-probabilistic thesis upheld); TR3/TR4/TR5 hooks and Phase 1/2 options (`tools=[]`, `strict_mcp_config=True`, `allowed_tools`) unchanged.
- [ ] `pytest tests/ -m "not integration"` passes with zero API calls; full suite green; **no Phase 1/2 regressions**.
- [ ] No new third-party dependencies (stdlib `json`/`random` only).

---

## COMPLETION CHECKLIST

- [ ] Task 0 verified `is_error` surfacing, `.handler` callability, and the `updatedInput` finding (recorded in `handoff_gate.py`).
- [ ] All tasks completed in order; each task's VALIDATE passed before moving on.
- [ ] Level 1–3 validation passes; Level 4 manual checks show transient-retry and over-limit→handoff.
- [ ] Deterministic suite proves TR6 categories + TR8 completeness without the model.
- [ ] `build_options()` changed only by the added `handoff_gate` matcher; `SYSTEM_PROMPT` changed only by TR6 guidance + TR7 few-shots.
- [ ] Acceptance criteria all met; EXECUTION NOTES appended for Phase 4.

---

## NOTES

**Locked design decisions (confirmed with the user before planning):**
1. **Venting calibration (TR7) — multi-turn deferred to Phase 4.** Phase 3 encodes the acknowledge→resolve→escalate-on-reiteration *criteria* in few-shots and validates single-turn signals (lone venting does not escalate; explicit request does). True multi-turn reiteration testing lands with Phase 4's conversation/compaction infrastructure (matches the PRD phase split).
2. **Flaky 503 (TR6) — deterministic seam.** `FLAKY_503_ENABLED` turns on; a `force_transient_failures(n)` test seam drives transient-then-success deterministically in unit tests, while live runs stay ~10% probabilistic. The deterministic suite stays 100% reproducible.
3. **Handoff (TR8) — model fills schema + code validates.** The model populates the enriched `escalate_to_human` schema; the `handoff_gate` PreToolUse hook is the deterministic completeness guarantee (deny→retry). Verified-flag backfill from `verified_store` via `updatedInput` is optional/best-effort, gated on Task 0.
4. **Retry (TR6) — model-driven.** The faithful reading of "the agent retries transient errors": tools surface a retryable transient error; the system prompt + few-shots teach category-driven retry, bounded by `max_turns`. No retry hook (retry is behavior, not a 100%-invariant).

**Design rationale & trade-offs:**
- **Envelope in the content text, not `structuredContent`:** the Phase 2 Task-0 finding (re-confirmed in SDK source this phase) proves `structuredContent` never reaches the model. Serializing `category=…/retryable=…` into the text is the only way the model can make category-driven decisions; `structuredContent` is kept for contract fidelity but is inert at runtime.
- **`handoff_gate` as a PreToolUse hook (deny→retry), not tool-internal validation:** reuses the exact deterministic mechanism proven in Phase 2 (TR3/TR4), gives access to `session_id` for the optional verified-stamp, and keeps the completeness guarantee separable and unit-testable from the tool's assembly logic.
- **`.handler` direct calls for TR6 tests:** the decorated `SdkMcpTool` exposes the raw async handler, so error categories are provable with zero API cost — no impl-extraction refactor, no change to the TR2-locked tool descriptions/schemas.
- **TR7 few-shots in the prompt:** escalation calibration is inherently probabilistic judgment — exactly the kind of behavior the system prompt is *for*. This is the one sanctioned prompt edit; it must not bleed into TR3/TR4/TR5 territory.

**Key risks / verify first:**
1. **`updatedInput` for MCP tools (Task 0).** Only the optional verified-stamp depends on it; the TR8 completeness guarantee does not. Drop the stamp if it doesn't work.
2. **Live venting calibration (Test 4).** Most model-dependent assertion; tune via few-shot wording, not by weakening the test. Hard guarantees are deterministic.
3. **Transient ordering in `lookup_order`.** The 503 check must precede unknown/mismatch checks or a transient gets misclassified as non-retryable.
4. **Flaky seam leakage across tests.** Process-global; the autouse `reset_flaky()` (Task 10) is mandatory, mirroring `verified_store.reset()`.

**Confidence (one-pass success): 8.5/10.** The single biggest Phase-2 unknown (the dropped-`structuredContent` shape) is now closed and re-confirmed in source; `.handler` callability removes the tool-testing risk; the deterministic guarantees (error categories, handoff completeness) are provable without the model; the seam keeps the suite reproducible. The residual unknowns are the optional `updatedInput` stamp (de-risked by making it optional) and live calibration stability (mitigated by deterministic proofs + tunable few-shots).

---

## EXECUTION NOTES (Phase 3 — implemented)

**Result:** All 10 tasks completed in order; every task's VALIDATE passed. Full suite green: **80 deterministic + 13 live = 93 passed**, zero API calls in the deterministic run. No Phase 1/2 regressions.

**Task 0 — `updatedInput` finding (RESOLVED: it works).** A throwaway smoke driver registered a PreToolUse hook returning `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {...}}}` for an in-process MCP tool and printed what the tool received. The injected field **did reach the tool** (`TOOL RECEIVED ARGS: {'marker': 'hello', 'injected_by_hook': 'STAMPED'}`). So the optional verified-stamp is **live**, not dropped: `handoff_gate`, on allow, overwrites `customer.verified` with the code-backed fact from `verified_store`. This is recorded in `src/hooks/handoff_gate.py`'s module docstring. (`is_error` surfacing and `.handler` callability were already source-confirmed and held in practice.)

**Deviation 1 — allow path returns `updatedInput`, not bare `{}`.** Task 6's VALIDATE snippet expected `good.get('hookSpecificOutput')` to be `None` on allow; because the verified-stamp is live, a complete handoff with a customer id returns a `hookSpecificOutput` carrying `updatedInput` (no `permissionDecision`). The operative invariant — "not denied" — holds. Tests assert on `permissionDecision != "deny"`, not on `hookSpecificOutput is None`.

**Deviation 2 — flaky probabilistic path pinned OFF for the whole suite.** Turning on `FLAKY_503_ENABLED = True` (production default) means `maybe_fail_transient()` has a ~10% random chance even with no forced failures — which would flake the validation/permission/success unit tests AND the non-transient live tests (business/escalation/venting). No test relies on the *probabilistic* path (every transient test forces its 503 via the seam), so the autouse `_reset_flaky` fixture in `conftest.py` saves, sets `FLAKY_503_ENABLED = False`, and restores it around each test — leaving the production default `True` untouched in source. This is the correct reading of the plan's "deterministic suite stays 100% reproducible" goal; the plan's `reset_flaky()` (forced-count only) was insufficient on its own.

**Deviation 3 — obsolete Phase-1 test updated.** `tests/test_fixtures.py::test_flaky_endpoint_inert_in_phase1` asserted `FLAKY_503_ENABLED is False` and `maybe_fail_transient() is None` — both deliberately changed by Phase 3. Replaced with `test_flaky_seam_is_deterministic`, which verifies the forced-failure countdown (`True, True, False`) under the now-pinned probabilistic path.

**Error-message wording (for Phase 4 calibration).** The actionable, category-naming error texts (e.g. *"…temporarily unavailable (HTTP 503). This is a transient error; retry the request."* and *"Order … is cancelled and cannot be refunded. Explain this to the customer; if they dispute it, escalate to a human."*) drove correct live behavior first-try: transient retried→resolved, business explained without looping. The TR7 few-shots (explicit→immediate, venting→acknowledge-first) produced the calibrated single-turn behavior with no tuning needed. If Phase 4's multi-turn venting-reiteration test proves flaky, the lever is the venting few-shot wording, not the assertion. The `handoff_gate` deny→retry never triggered in live runs because the enriched schema + description got the model to fill all fields on the first call — but the deterministic suite proves the gate denies/repairs incomplete handoffs regardless.

**Phase 4 carry-forward.** Multi-turn venting reiteration (acknowledge→resolve→escalate-on-reiteration) is deferred here by the locked decision and lands with Phase 4's conversation/compaction infrastructure (case-facts block TR9, multi-issue decomposition FR5). The `reason_for_escalation` enum and the handoff JSON shape are stable contracts Phase 4 can rely on.
