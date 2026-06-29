# PRD — Customer Support Resolution Agent

> **Source of truth:** [`01-customer-support-resolution-agent.md`](./01-customer-support-resolution-agent.md). This PRD expands that spec into an implementation-ready document. Where the two diverge, the original spec's TR1–TR9 and acceptance criteria win.
>
> **Status:** Greenfield, spec-driven, no implementation yet · **Difficulty:** ●●○ · **Effort:** 2–3 days · maps to CCA-F Exam Scenario 1.

---

## 1. Executive Summary

The Customer Support Resolution Agent is a production-style, **agentic** support resolver for a mid-size retailer. It accepts free-text customer messages and resolves common tier-1 intents — order status, returns/refunds, billing disputes, account updates — end-to-end, reaching backend systems exclusively through **MCP tools**. It is built on the **Claude Agent SDK** with mocked backends, so the focus stays on agent behavior rather than payment or auth infrastructure.

The product's reason for being is the distinction between *probabilistic prompt guidance* and *deterministic enforcement*. Because tool calls here move money and touch accounts, rules that must hold 100% of the time (refund limits, identity prerequisites, data normalization) are implemented as **code and hooks**, never as system-prompt instructions. The agent must know when to act autonomously, when a hard rule forbids action, and when to hand a case to a human with a self-contained summary.

**MVP goal:** Achieve **≥80% first-contact resolution** on a 20-case scripted suite while enforcing every guardrail with 100% reliability — no over-limit refund ever issued autonomously, no action ever taken on a misidentified customer, and every escalation accompanied by a complete handoff. Validation asserts on **tool calls and outcomes, not on model wording**.

## 2. Mission

**Mission:** Deflect 80%+ of tier-1 support contacts without sacrificing safety, by resolving what is safely resolvable and escalating the rest with full context.

**Core principles:**

1. **Deterministic over probabilistic.** Any invariant that must hold every time is code or a hook — never a prompt instruction. A prompt-based refund limit is an automatic failure.
2. **Least privilege.** The agent has access to exactly four scoped tools and nothing more.
3. **Verify before you act.** No order, account, or financial operation occurs before customer identity is programmatically verified.
4. **Escalate with calibration, not reflex.** Explicit human requests escalate immediately; first-time venting does not. Ambiguity (e.g., duplicate customers) prompts a clarifying question — never a guess.
5. **Ground truth is behavior.** Success is measured on tool calls and outcomes, not on the agent's prose.

## 3. Target Users

| Persona | Description | Technical comfort | Key needs / pain points |
|---|---|---|---|
| **End customer** | A retail customer with an order issue, refund request, billing dispute, or account change. | Low — expects natural-language chat. | Fast, correct resolution; not being mis-identified; a human when they need one. |
| **Support operator (escalation target)** | The human who receives escalated cases. | High. | A self-contained handoff summary they can act on **without** seeing the transcript. |
| **Builder / maintainer (you)** | Engineer building and regression-testing the agent. | Expert. | Deterministic guardrails, a scripted validation suite that doubles as a regression gate, observable tool-call behavior. |
| **Support operations lead** | Owns deflection rate and safety posture. | Medium. | Provable enforcement (100% of over-limit refunds redirected), measurable first-contact resolution ≥80%. |

## 4. MVP Scope

### In Scope ✅

**Core Functionality**
- ✅ Free-text intake resolving order status, return/refund, billing dispute, account update (FR1)
- ✅ Identity verification gate before any order/account/financial operation (FR2, TR4)
- ✅ In-policy refund processing; out-of-policy routed to human (FR3, TR3)
- ✅ Calibrated escalation: explicit request, policy gap, stalled progress (FR4, TR7)
- ✅ Multi-issue message → resolve each → one unified reply (FR5)
- ✅ Case facts (amounts, order IDs, dates) accurate across multi-turn conversation (FR6, TR9)

**Technical**
- ✅ `stop_reason`-driven agentic loop, `tool_use`→continue / `end_turn`→finish (TR1)
- ✅ Exactly four richly-described MCP tools, two deliberately similar (TR2)
- ✅ Deterministic refund PreToolUse hook (TR3)
- ✅ Prerequisite gate in code (TR4)
- ✅ PostToolUse date normalization to ISO 8601 (TR5)
- ✅ Structured tool errors with category + retryability (TR6)
- ✅ Self-contained JSON handoff summary (TR8)
- ✅ Case-facts block injected every prompt + verbose output trimming (TR9)

**Integration**
- ✅ Mocked backends with seeded fixtures (customers, orders, duplicate-name pair, flaky 503 ~10% endpoint)

**Validation**
- ✅ Scripted scenario suite (8 scenario types, 20+ cases) asserting on tool calls/outcomes

### Out of Scope ❌

- ❌ Polished chat UI (Next.js) — stretch goal only
- ❌ Real payment processing
- ❌ Real auth / billing infrastructure
- ❌ Training or fine-tuning any model
- ❌ Persistent database (mock fixtures only)
- ❌ Multi-language support
- ❌ Confidence-scored auto-vs-human routing (future)
- ❌ Supervisor/auditor agent (future)
- ❌ Real FastAPI + Postgres backend (future)

## 5. User Stories

1. **As a customer, I want to ask "where's my order?" in plain language, so that I get its status without filling out a form.**
   *Example:* "Hi, what's the status of my order?" → agent verifies identity, looks up order, returns status + ISO-normalized dates.

2. **As a customer, I want a small refund processed immediately, so that I don't wait for a human.**
   *Example:* "$40 item arrived broken" → identity verified → `process_refund($40)` succeeds (under limit).

3. **As the business, I want any refund over policy redirected to a human, so that no large refund is ever issued autonomously.**
   *Example:* "Refund my $900 order" → PreToolUse hook intercepts → escalation, never a direct refund.

4. **As a customer, I want to reach a human when I ask, so that I'm not trapped with a bot.**
   *Example:* "Get me a manager" → immediate escalation with handoff summary.

5. **As a venting customer, I want my frustration acknowledged before escalation, so that I feel heard.**
   *Example:* First angry message → acknowledge + attempt resolution; only escalate if reiterated.

6. **As a customer with a common name, I want to be asked for another identifier, so that I'm not confused with someone else.**
   *Example:* "John Smith" matches two records → agent asks for email/order ID, never guesses.

7. **As a customer, I want a message with two problems handled in one reply, so that I don't repeat myself.**
   *Example:* "Where's order A, and refund order B" → both resolved → single unified response.

8. **As a support operator, I want a complete handoff summary, so that I can resolve the case without the transcript.**
   *Example:* Escalation emits JSON with customer, order, root cause, actions taken, recommended action, reason.

**Technical stories**

9. **As a builder, I want the loop to terminate only on `end_turn`, so that completion is never inferred by parsing text.**
10. **As a builder, I want transient 503s retried but business errors explained, so that error handling is category-driven.**
11. **As a builder, I want exact $ amounts and order IDs to survive a simulated `/compact`, so that context compaction never corrupts case facts.**

## 6. Core Architecture & Patterns

**High-level approach:** A single `AgentDefinition` (Claude Agent SDK) with `allowed_tools` scoped to exactly four MCP tools. The agentic loop runs the model, dispatches tool calls through an in-process MCP server backed by mocks, and feeds `tool_result`s back. **Hooks wrap the loop** and carry every hard invariant.

```
customer-support/
├── docs/
│   ├── 01-customer-support-resolution-agent.md   # source-of-truth spec
│   └── 02-customer-support-prd.md                 # this PRD
├── src/
│   ├── agent.py            # AgentDefinition, system prompt, allowed_tools
│   ├── loop.py             # stop_reason-driven agentic loop (TR1)
│   ├── tools/
│   │   ├── server.py       # MCP server registration
│   │   ├── get_customer.py
│   │   ├── lookup_order.py
│   │   ├── process_refund.py
│   │   └── escalate_to_human.py
│   ├── hooks/
│   │   ├── pretool_refund_gate.py   # TR3 deterministic refund limit
│   │   ├── prerequisite_gate.py     # TR4 identity-before-action
│   │   └── posttool_normalize.py    # TR5 date → ISO 8601
│   ├── context/
│   │   └── case_facts.py            # TR9 persisted facts block + trimming
│   ├── errors.py           # structured error envelope (TR6)
│   ├── handoff.py          # TR8 self-contained JSON summary
│   └── mocks/
│       └── fixtures.py     # customers, orders, duplicate pair, flaky 503
└── tests/
    └── test_scenarios.py   # scripted suite = regression gate
```

**Key patterns:**
- **Deterministic guardrails as hooks**, not prompt text (TR3, TR4, TR5).
- **`stop_reason` state machine** for the loop; max-iteration cap is a *backstop only* (TR1).
- **Structured error envelope** returned by all tools (TR6).
- **Case-facts block** injected into every prompt, kept *outside* summarized history so it survives compaction (TR9).
- **System prompt scoped to behavior/escalation judgment**, deliberately avoiding the "always verify the customer" over-trigger trap.

## 7. Tools / Features

All four tools return a **structured result or structured error** (see §10). Two are deliberately similar (`get_customer` vs `lookup_order`) and must be disambiguated purely by rich descriptions.

| Tool | Purpose | Key inputs | Notes / edge cases |
|---|---|---|---|
| **`get_customer`** | Verify and identify a customer; prerequisite for everything else. | name, email, or phone | Returns **multiple matches** for the duplicate-name pair → agent must ask for an extra identifier (TR7). Sets verified customer ID used by the prerequisite gate (TR4). |
| **`lookup_order`** | Retrieve order details/status for a *verified* customer. | verified customer ID, order ID | Blocked until `get_customer` succeeds (TR4). One backend field is the **flaky 503 ~10%** endpoint (TR6 transient). Returns dates in heterogeneous formats → normalized by PostToolUse hook (TR5). |
| **`process_refund`** | Issue a refund within policy. | verified customer ID, order ID, amount | **PreToolUse hook** redirects any amount > policy limit (~$500) to escalation (TR3). Blocked before verification (TR4). |
| **`escalate_to_human`** | Hand off to a human with a complete summary. | handoff JSON (customer, order, root cause, actions taken, recommended action, reason) | Emits a **self-contained** summary (TR8). Triggered by hooks, by explicit request, or by escalation calibration (TR7). |

**Feature highlights:**
- **Deterministic refund guardrail (TR3):** intercept `process_refund`, compare amount to policy limit, redirect over-limit to escalation — 100% of the time, provable across 20+ test cases.
- **Prerequisite gate (TR4):** `lookup_order`/`process_refund` are programmatically impossible before a verified customer ID exists.
- **Data normalization (TR5):** PostToolUse hook converts Unix timestamp / `"Mar 5, 2025"` / ISO inputs to ISO 8601 before the model reasons over them.
- **Escalation calibration (TR7):** explicit criteria + 2–4 few-shot examples; multi-match → ask for identifier.
- **Context hygiene (TR9):** case-facts block survives compaction; tool outputs trimmed from 40+ fields to the ~5 that matter.

## 8. Technology Stack

| Layer | Choice | Version / notes |
|---|---|---|
| Language | Python | **3.10** |
| Agent framework | `claude-agent-sdk` | **Not yet installed** — add at build start |
| Model | Claude (latest capable) | Opus 4.8 / Sonnet 4.6 per task; default to latest |
| LLM SDK | `anthropic` | 0.109.1 (installed) |
| MCP | In-process MCP server library | **Not yet installed** — add at build start |
| Testing | `pytest` | **Not yet installed** — add at build start |
| Embeddings (if needed) | `voyageai` | 0.4.1 (installed; likely unused for MVP) |
| Env management | Shared workspace venv | `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv` |
| Secrets | `.env` at workspace root | `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` (one level above `projects/`) |

**Install at build start (Phase 1):** `pip install claude-agent-sdk <mcp-server-lib> pytest` into the shared venv.

## 9. Security & Configuration

- **Authentication:** None for MVP (mocked backend, no real auth infra — out of scope). Customer *identity verification* is a functional gate (TR4), not a security/auth system.
- **Authorization model:** Least privilege via `allowed_tools` scoped to exactly four tools (D2.3).
- **Configuration:** API keys loaded from workspace-root `.env`; policy limit (~$500) and fixture data centralized as config/constants so tests can parameterize them.
- **Security in scope:** deterministic enforcement of refund limit and identity prerequisite; never acting on a misidentified customer.
- **Security out of scope:** real payment processing, real auth/billing, DLP, transport security, PII handling beyond mock fixtures.
- **Deployment:** Local/dev only for MVP (CLI/REPL acceptable). Production deployment is a future consideration.

## 10. Structured Error & Handoff Contracts

*(In lieu of a network API — the surface here is the tool-result envelope and handoff JSON.)*

**Tool error envelope (TR6):**
```json
{
  "isError": true,
  "errorCategory": "transient | validation | business | permission",
  "isRetryable": true,
  "message": "Human-readable explanation."
}
```
- `transient` (e.g., 503) → agent **retries**.
- `business` → agent **explains**, does not blindly retry.
- `validation` / `permission` → not retried; surfaced appropriately.

**Handoff summary (TR8)** — self-contained, no transcript needed:
```json
{
  "customer": { "id": "...", "name": "...", "verified": true },
  "order": { "id": "...", "status": "...", "amount": 0.0 },
  "root_cause": "...",
  "actions_taken": ["..."],
  "recommended_action": "...",
  "reason_for_escalation": "explicit_request | policy_gap | over_limit_refund | stalled"
}
```

**Case-facts block (TR9)** — injected into every prompt, outside summarized history:
```
CASE FACTS (verbatim, do not paraphrase):
- customer_id: ...
- order_id(s): ...
- amounts: $...
- dates (ISO 8601): ...
```

## 11. Success Criteria

**MVP success =** ≥80% first-contact resolution on a 20-case scripted suite **with** every guardrail enforced 100%.

**Functional / acceptance checks** (from spec — non-negotiable):
- ✅ Loop continues/stops purely on `stop_reason`; no text-parsing, no cap-as-primary.
- ✅ 100% of over-limit refunds redirected to escalation by the hook (test 20+ cases).
- ✅ `process_refund` provably impossible before a verified `get_customer`.
- ✅ Transient (503) errors retried; business errors explained; non-retryable errors not retried.
- ✅ Explicit "get me a manager" escalates immediately; first-time venting does not.
- ✅ Handoff JSON contains everything a human needs without the transcript.
- ✅ Exact $ amounts / order IDs persist verbatim after a simulated `/compact`.
- ✅ Measured first-contact resolution ≥80% on the 20-case suite.

**Quality indicators:** correct tool selection between the two similar tools; no over-triggered verification; clean unified replies for multi-issue messages.

## 12. Implementation Phases (PIV)

### Phase 1 — Loop + Tools
- **Goal:** Resolve a simple order-status query end-to-end.
- **Deliverables:** ✅ `stop_reason` loop · ✅ four MCP tools with rich descriptions · ✅ mock fixtures · ✅ `allowed_tools` scoping.
- **Validate:** loop terminates only on `end_turn`; correct tool chosen; order-status query resolved E2E.

### Phase 2 — Guardrails
- **Goal:** Deterministic enforcement.
- **Deliverables:** ✅ prerequisite gate (TR4) · ✅ refund PreToolUse hook (TR3) · ✅ PostToolUse date normalization (TR5).
- **Validate:** over-limit refunds blocked 100% (20+ cases); `process_refund` impossible pre-verification; dates compare correctly.

### Phase 3 — Errors + Escalation
- **Goal:** Robust failure handling and calibrated handoff.
- **Deliverables:** ✅ structured error envelope (TR6) · ✅ escalation calibration + few-shots (TR7) · ✅ self-contained handoff JSON (TR8).
- **Validate:** transient retried, business explained, non-retryable not retried; multi-match asks for ID; explicit request escalates immediately; handoff self-contained.

### Phase 4 — Context + Multi-issue
- **Goal:** Long-conversation reliability and multi-issue resolution.
- **Deliverables:** ✅ case-facts block (TR9) · ✅ verbose output trimming · ✅ multi-issue decomposition → unified reply (FR5).
- **Validate:** exact amounts/order IDs survive simulated `/compact`; 2-issue message → one correct unified reply; full 20-case suite ≥80%.

**Timeline:** ~2–3 days total; roughly half a day per phase plus suite hardening.

## 13. Future Considerations

- Minimal chat UI (Next.js) or polished CLI REPL.
- Confidence-scored auto-vs-human routing.
- A second **supervisor agent** auditing a sample of resolutions.
- Swap mock backend for a real **FastAPI + Postgres** service.
- Multi-language intake; richer intent taxonomy; analytics on deflection rate.

## 14. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Guardrail implemented as prompt text** instead of code (auto-fail). | Refund limit and prerequisite gate live in hooks/code; tests assert enforcement on tool calls, parameterized over 20+ cases. |
| **Loop terminates by parsing assistant text** or relies on iteration cap as primary stop. | Drive strictly off `stop_reason`; cap is backstop only; add an explicit test that the loop ends solely on `end_turn`. |
| **Two similar tools mis-selected** (`get_customer` vs `lookup_order`). | Invest in rich, disambiguating descriptions (purpose, formats, examples, when-to-use-vs-alternatives); assert correct tool chosen in tests. |
| **Case facts corrupted by compaction.** | Keep case-facts block outside summarized history, injected every prompt; test verbatim survival across simulated `/compact`. |
| **Over-triggered verification** ("always verify") harming UX/resolution rate. | Keep system prompt focused on behavior; verify only before order/account/financial ops; measure first-contact resolution to catch regressions. |
| **Flaky 503 mishandled** (blind retry or premature give-up). | Category-driven retry: retry only `transient`/`isRetryable`; cap retries; explain `business` errors. |

## 15. Appendix

**Related documents**
- [`01-customer-support-resolution-agent.md`](./01-customer-support-resolution-agent.md) — source-of-truth spec (TR1–TR9, acceptance criteria, CCA-F coverage).
- Project `CLAUDE.md` — build rules and the deterministic-vs-probabilistic design distinction.

**Read-first references**
- Building agents with the Claude Agent SDK.
- Agent SDK [Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks) & [Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents).
- Writing effective tools for AI agents.

**CCA-F coverage map**

| Task statement | Exercised by |
|---|---|
| D1.1 Agentic loop / stop_reason / anti-patterns | TR1, Phase 1 |
| D1.4 Enforcement & handoff patterns | TR4, TR8 |
| D1.5 Hooks (PreToolUse/PostToolUse) | TR3, TR5 |
| D2.1 Tool descriptions & disambiguation | TR2 |
| D2.2 Structured MCP errors | TR6 |
| D2.3 Tool scoping (least privilege) | Architecture |
| D5.1 Context preservation (case facts, trimming) | TR9 |
| D5.2 Escalation & ambiguity resolution | TR7, TR8 |
