# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: greenfield, spec-driven

This directory currently contains **only a specification** — `01-customer-support-resolution-agent.md` — and no implementation. That spec is the source of truth: it defines a Customer Support Resolution Agent built on the **Claude Agent SDK**, with mocked backends reached through MCP tools. Read it in full before writing code; the technical requirements (TR1–TR9) and acceptance criteria are non-negotiable contracts, not suggestions.

## Environment

- Python **3.10** via a **shared virtualenv at the workspace root**: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv` (this project does not have its own). Activate it or invoke `../../.venv/bin/python`.
- API keys live in the workspace-root `.env` (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`) — one level above `projects/`. Load from there.
- Currently installed: `anthropic` SDK only. The spec's stack — `claude-agent-sdk`, an MCP server library, and `pytest` — is **not yet installed**; add it when starting the build (prefer `pnpm`-style discipline noted in global instructions only applies to Node; this is Python, use `pip` into the shared venv).
- Per global instructions: use `pytest` for tests and check for an existing `tests/` directory before creating new test files.

## The core design distinction (read this first)

The entire point of this build is **deterministic enforcement vs. probabilistic prompt guidance**. Where the spec says a rule must hold 100% of the time, it must be **code**, never a system-prompt instruction:

- **Refund limit (TR3):** a **PreToolUse hook** intercepts `process_refund` and redirects any amount over the policy limit (~$500) to escalation. A prompt asking the model to "not refund over $500" is an automatic failure of this requirement.
- **Prerequisite gate (TR4):** `lookup_order` and `process_refund` are programmatically blocked until `get_customer` has returned a verified customer ID — enforced in code, not prompted.
- **Data normalization (TR5):** a **PostToolUse hook** converts heterogeneous tool outputs (Unix timestamp / `"Mar 5, 2025"` / ISO 8601) to ISO 8601 *before* the model reasons over them.

Conversely, keep the **system prompt focused on behavior and escalation judgment**, not on coupling a tool to every turn. Avoid the "always verify the customer" over-trigger trap.

## Agentic loop rules (TR1) — common failure modes

- Drive the loop off `stop_reason`: continue on `"tool_use"`, finish on `"end_turn"`.
- Append every `tool_result` to history before the next turn.
- **Anti-patterns that fail acceptance:** parsing assistant text to detect completion; using a max-iteration cap as the *primary* stop condition (it's allowed only as a backstop).

## Tool & error design

- Exactly **four** MCP tools, scoped via `allowed_tools` (least privilege): `get_customer`, `lookup_order`, `process_refund`, `escalate_to_human` (TR2). Two tools are deliberately similar — disambiguate them purely through rich descriptions (purpose, input formats, example values, edge cases, when-to-use-vs-alternatives) so selection stays reliable.
- Tools return **structured errors** (TR6): `isError` with `errorCategory` (`transient` / `validation` / `business` / `permission`), `isRetryable`, and a human-readable message. The agent retries `transient` (e.g., a 503), explains `business` errors, and never blindly retries non-retryable ones.
- Mock backends behind the tools with seeded fixtures: a few customers, orders, a **duplicate-name pair** (forces the multi-match → ask-for-extra-identifier path, TR7), and a **flaky endpoint returning 503 ~10% of the time** (exercises transient retry).

## Escalation, handoff, and context

- **Escalation calibration (TR7):** explicit criteria with 2–4 few-shot examples — immediate on an explicit human request; acknowledge→resolve→escalate-on-reiteration for venting; escalate on policy gaps. On multiple `get_customer` matches, ask for another identifier — never guess.
- **Handoff (TR8):** on escalation emit a self-contained JSON summary (customer, order, root cause, actions taken, recommended action, reason). The human cannot see the transcript, so it must stand alone.
- **Context hygiene (TR9):** persist transactional "case facts" (amounts, order IDs, dates) in a block injected into **every** prompt, kept *outside* summarized history so they survive compaction; trim verbose tool outputs (40+ fields → the ~5 that matter).

## Validation is ground truth, not prose

Build a **scripted scenario suite** (happy path, over-limit refund, duplicate customer, transient failure, venting customer, explicit escalation, policy gap, multi-issue) and **assert on tool calls and outcomes — not on the model's wording**. This suite doubles as the regression gate. Targets from the acceptance criteria: 100% of over-limit refunds redirected (test 20+ cases), `process_refund` provably impossible before verification, exact $ amounts/order IDs surviving a simulated `/compact`, and ≥80% first-contact resolution on a 20-case suite.

## Build order (PIV phases)

1. Loop + four tools → resolve a simple order-status query end-to-end.
2. Guardrails → prerequisite gate, refund PreToolUse hook, PostToolUse date normalization.
3. Errors + escalation → structured errors, escalation calibration, handoff summary.
4. Context + multi-issue → case-facts block, output trimming, multi-issue decomposition into one unified reply.
