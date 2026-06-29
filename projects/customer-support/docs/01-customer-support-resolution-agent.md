# Project 01 — Customer Support Resolution Agent

> **Pitch:** Build a production-style support agent that resolves returns, billing disputes, and account
> issues end-to-end — knowing when to act, when to enforce a hard rule, and when to hand off to a human.
> **Primary domains:** D1 Agentic Architecture · D2 Tool Design & MCP · D5 Context & Reliability.
> **Difficulty:** ●●○ · **Effort:** 2–3 days · maps to **official Exam Scenario 1**.

## Problem statement

A mid-size retailer wants to deflect 80%+ of tier-1 support contacts without sacrificing safety. You are
building an **agentic** support resolver on the Claude Agent SDK. It talks to backend systems through MCP
tools and must hit **≥80% first-contact resolution** while **escalating correctly** — never issuing a
large refund autonomously, never acting on a misidentified customer. Get the agentic loop, the guardrails,
and the escalation calibration right.

## Background / why it matters

This is the canonical "agent with consequences" build: tool calls move money and touch accounts, so it
exercises the difference between *probabilistic* prompt guidance and *deterministic* enforcement, plus the
judgment of when to resolve vs escalate. It's the most direct rehearsal of Exam Domain 1 + the support scenario.

## Goals & non-goals

- **Goals:** a correct agentic loop; 4 well-described MCP tools; a deterministic refund guardrail; calibrated
  escalation; a self-contained human handoff; context that survives long conversations.
- **Non-goals:** a polished UI, real payment processing, auth/billing infra, or training any model. Mock the
  backend. (UI is a stretch goal.)

## Functional requirements

- FR1. Accept a free-text customer message and resolve common intents: order status, return/refund request,
  billing dispute, account update.
- FR2. Verify customer identity before any order/account/financial operation.
- FR3. Process refunds **only** within policy; route larger or out-of-policy refunds to a human.
- FR4. Escalate to a human when the customer asks for one, when policy is silent/ambiguous, or when the agent
  can't make progress — with a complete handoff summary.
- FR5. Handle a message containing **multiple issues** by resolving each and returning one unified reply.
- FR6. Maintain accurate case facts (amounts, order IDs, dates) across a multi-turn conversation.

## Technical requirements (mapped to CCA-F task statements)

- **TR1 — Agentic loop (D1.1).** Drive the loop off `stop_reason`: continue on `"tool_use"`, finish on
  `"end_turn"`. Append every `tool_result` to history before the next turn. **No** anti-patterns: don't parse
  assistant text for completion, don't use a max-iteration cap as the *primary* stop (keep it only as a backstop).
- **TR2 — MCP tools (D2.1).** Define `get_customer`, `lookup_order`, `process_refund`, `escalate_to_human`
  with rich descriptions (purpose, input formats, example values, edge cases, when-to-use-vs-alternatives).
  Include two deliberately similar tools and disambiguate them by description so selection stays reliable.
- **TR3 — Deterministic guardrail (D1.5).** A **PreToolUse hook** intercepts `process_refund` and redirects any
  amount over the policy limit (e.g., \$500) to escalation. Prove it blocks 100% of over-limit attempts — a
  prompt instruction is *not* acceptable here.
- **TR4 — Prerequisite gate (D1.4).** Programmatically block `lookup_order`/`process_refund` until
  `get_customer` has returned a verified customer ID.
- **TR5 — Data normalization (D1.5).** A **PostToolUse hook** normalizes heterogeneous tool outputs (Unix
  timestamp vs `"Mar 5, 2025"` vs ISO 8601) to ISO 8601 before the model reasons on them.
- **TR6 — Structured errors (D2.2).** Tools return `isError` with `errorCategory`
  (transient/validation/business/permission), `isRetryable`, and a human-readable message. The agent retries
  transient errors, explains business errors, and never blindly retries non-retryable ones.
- **TR7 — Escalation calibration (D5.2).** Encode explicit escalation criteria with 2–4 few-shot examples
  (immediate on explicit human request; acknowledge→resolve→escalate-on-reiteration for venting; escalate on
  policy gaps). Ask for an extra identifier when `get_customer` returns multiple matches — never guess.
- **TR8 — Structured handoff (D1.4 / D5.2).** On escalation, emit a self-contained JSON summary (customer,
  order, root cause, actions taken, recommended action, reason) — the human can't see the transcript.
- **TR9 — Context hygiene (D5.1).** Persist transactional "case facts" in a block included every prompt,
  outside summarized history; trim verbose tool outputs (40+ fields → the ~5 that matter).

## Architecture guidance (references, not code)

- One `AgentDefinition` with `allowed_tools` scoped to exactly the four tools (least privilege). Mock backends
  behind the MCP tools with seeded fixtures (a few customers, orders, a duplicate-name pair, a flaky endpoint
  that returns a 503 ~10% of the time to exercise transient handling).
- Hooks live around the loop; the refund gate and prerequisite gate are deterministic code, not prompt text.
- Keep the system prompt focused on *behavior/escalation*, not on associating a tool with every turn (avoid the
  "always verify the customer" over-trigger trap).

## Build phases (PIV)

1. **Loop + tools.** Implement the `stop_reason` loop and the four MCP tools with strong descriptions; resolve
   a simple order-status query end-to-end. *Validate:* loop terminates only on `end_turn`; correct tool chosen.
2. **Guardrails.** Add the prerequisite gate + refund PreToolUse hook + PostToolUse date normalization.
   *Validate:* over-limit refunds are blocked 100%; dates compare correctly.
3. **Errors + escalation.** Add structured errors and escalation calibration + handoff summary.
   *Validate:* transient retried, business explained, multi-match asks for ID, handoff is self-contained.
4. **Context + multi-issue.** Add the case-facts block, output trimming, and multi-issue decomposition.
   *Validate:* exact amounts survive a long conversation; a 2-issue message gets one correct unified reply.

## Acceptance criteria

- [ ] Loop continues/stops purely on `stop_reason`; no text-parsing or cap-as-primary.
- [ ] 100% of over-limit refunds are redirected to escalation by the hook (test 20+ cases).
- [ ] `process_refund` is impossible before a verified `get_customer` (test the gate).
- [ ] Transient (503) errors are retried; business errors are explained; non-retryable errors aren't retried.
- [ ] Explicit "get me a manager" escalates immediately; first-time venting does not.
- [ ] Handoff JSON contains everything a human needs without the transcript.
- [ ] Exact \$ amounts/order IDs persist verbatim after a simulated `/compact`.
- [ ] Measured first-contact resolution ≥80% on a 20-case scripted suite.

## Validation strategy

Write a scripted scenario suite (happy path, over-limit refund, duplicate customer, transient failure,
venting customer, explicit escalation, policy gap, multi-issue). Measure resolution rate and guardrail
enforcement as **ground truth** (assert on tool calls and outcomes, not on prose). This suite is also your
regression gate for later changes.

## Stretch goals

- A minimal chat UI (Next.js) or CLI REPL. · Confidence-scored auto-vs-human routing. · A second
  "supervisor" agent that audits a sample of resolutions. · Swap the mock backend for a real FastAPI+Postgres service.

## CCA-F coverage

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

**Read first:** Building agents with the Claude Agent SDK; Agent SDK [Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)
& [Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents); Writing effective tools for AI agents.
