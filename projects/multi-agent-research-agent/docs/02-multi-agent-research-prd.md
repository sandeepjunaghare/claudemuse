# PRD — Multi-Agent Research System

> **Source of truth:** [`02-multi-agent-research-system.md`](./02-multi-agent-research-system.md). This PRD expands that spec into an implementation-ready document. Where the two diverge, the original spec's **TR1–TR10**, **FR1–FR5**, and acceptance criteria win.
>
> **Status:** Greenfield, spec-driven, no implementation yet · **Difficulty:** ●●● · **Effort:** 3–5 days · maps to CCA-F **Exam Scenario 3** (D1 Agentic Architecture — the 27% centerpiece).

---

## 1. Executive Summary

The Multi-Agent Research System is a **hub-and-spoke** research assistant that turns a broad, open-ended question ("impact of AI on creative industries") into a complete, **cited** briefing. A lead **coordinator** decomposes the topic, dispatches specialized subagents that each explore in an **isolated context window and in parallel**, and then synthesizes their distilled findings into a structured report. It is built on the **Claude Agent SDK** with a **mocked search backend**, so the focus stays on orchestration behavior rather than on a real retrieval stack.

The product's reason for being is that multi-agent orchestration is the highest-weight, hardest-to-get-right agentic pattern. It is only justified when a task has **breadth**, benefits from **parallelism**, and strains a single **context window** — and it costs roughly **15× a single-agent chat** in tokens. So the system must earn that cost: cover the *whole* topic (not one facet), survive a subagent failure without aborting or silently dropping results, and never lose a claim's source or date. Every hard property — coverage, provenance, partial-result handling — is validated on **structure**, not on the model's prose.

**MVP goal:** From a broad research question, produce a structured report where **100% of claims carry a source**, coverage spans **all major facets** of the topic, **parallel spawning measurably beats sequential** on a multi-subtopic query, a **simulated subagent timeout yields a usable, gap-annotated report** (no abort, no silent empty), and **two conflicting sources both appear with attribution and dates** rather than one being arbitrarily chosen.

## 2. Mission

**Mission:** Deliver on-demand, fully-cited research briefings that cover a topic's full breadth by orchestrating parallel specialist subagents — and prove, on every run, that the multi-agent cost bought coverage, resilience, and provenance a single agent could not.

**Core principles:**

1. **Coordinator owns everything.** All decomposition, delegation, aggregation, and error handling live in one lead. Subagents never talk to each other.
2. **Context is explicit, not inherited.** A subagent knows only what its prompt tells it. Findings return as distilled ~1–2k-token summaries — detail stays isolated.
3. **Justify the fan-out.** Multi-agent is for breadth / parallelism / context pressure. Narrow queries take a single-agent fallback path.
4. **Never lose a source.** Every claim carries a source and a date. Conflicting credible sources are both preserved with attribution — never silently resolved.
5. **Degrade, don't abort.** A failing subagent produces a structured failure and partial results; the report continues with the gap annotated.
6. **Ground truth is structure.** Success is measured on coverage, citations, and partial-result handling — not on the report's wording.

## 3. Target Users

| Persona | Description | Technical comfort | Key needs / pain points |
|---|---|---|---|
| **Research requester** | Analyst/PM/exec who wants an on-demand briefing on a broad topic. | Low–medium — asks in natural language. | Breadth (no missed facets), trustworthy citations, honest flagging of what's unknown. |
| **Downstream reader** | Consumes the cited report to make a decision. | Medium. | Traceable claims (source + date), conflicts surfaced rather than hidden, gaps marked. |
| **Builder / maintainer (you)** | Engineer building and regression-testing the orchestration. | Expert. | Deterministic topology, observable `Task` fan-out, a seeded corpus that makes every failure mode reproducible. |
| **Architecture reviewer** | Evaluates whether multi-agent was the right call (and the exam grader). | High. | Evidence the fan-out paid off (latency, coverage), a written cost justification + single-agent fallback. |

## 4. MVP Scope

### In Scope ✅

**Core Functionality**
- ✅ Accept a research question → return a structured report with sections, claims, citations (FR1)
- ✅ Decompose the topic into subtopics that cover the whole space, assigned without heavy duplication (FR2, TR4)
- ✅ Run independent subagents in parallel; aggregate only through the coordinator (FR3, TR1, TR2)
- ✅ On subagent failure, continue with partial results and mark the gap (FR4, TR7)
- ✅ Preserve every claim's source and date; flag conflicting values instead of picking one (FR5, TR8)
- ✅ Iterative refinement: detect coverage gaps and re-delegate until sufficient (TR5)
- ✅ Single-agent fallback path for narrow queries (TR3, TR10)

**Technical**
- ✅ Coordinator–subagent topology; subagents talk only to the coordinator (TR1)
- ✅ Coordinator `allowedTools` includes `"Task"`; all context passed explicitly per subagent (TR2)
- ✅ Parallel spawning via **multiple `Task` calls in one coordinator response** (TR2)
- ✅ Dynamic subagent selection — only invoke the subagents a query needs (TR3)
- ✅ Scope partitioning with coverage verification against known facets (TR4)
- ✅ Iterative refinement loop re-invoking synthesis until coverage sufficient (TR5)
- ✅ Context isolation — subagents return distilled ~1–2k-token summaries, not transcripts (TR6)
- ✅ Structured error propagation: failure type, attempted query, partial results, alternatives; access-failure vs. valid-empty distinction; 1–2 local retries before propagating (TR7)
- ✅ Provenance: structured claim→source mappings (claim, source, excerpt, publication date); conflict + temporal handling preserved through synthesis (TR8)
- ✅ Coverage annotations: well-supported vs. gapped areas, rendered by content type (tables for figures, prose for analysis) (TR9)
- ✅ Cost discipline: documented multi-agent justification + measured token usage (TR10)

**Integration**
- ✅ Mocked `web_search` over a **seeded corpus** engineered to trigger every failure mode (4+ facet topic, two conflicting credible sources, a differently-dated source, a timeout endpoint)
- ✅ Runnable entry point that takes a question and prints/returns a report

### Out of Scope ❌

- ❌ A real search backend or live web retrieval (stretch: MCP search server)
- ❌ Beating SOTA research quality; long-form editorial polish
- ❌ Hosting / deployment infrastructure / UI
- ❌ Session forking to compare decomposition strategies (stretch, D1.7)
- ❌ Crash-recovery via reloadable state manifests (stretch, D5.4)
- ❌ An LLM-judge grading rubric for coverage/citation scoring (stretch)
- ❌ Authentication / multi-tenant access control

## 5. User Stories

1. **As a research requester,** I want to ask a broad question and get back a sectioned, cited report, **so that** I have a trustworthy briefing without doing the reading myself.
   - *Example:* "Impact of AI on creative industries" → sections on visual art, music, writing, and film, each with cited claims.
2. **As a research requester,** I want the report to cover the *whole* topic, **so that** I'm not misled by a briefing that silently only covered one facet.
   - *Example:* The report never returns "only visual arts" for a four-facet topic; a coverage check flags the omission and re-delegates.
3. **As a downstream reader,** I want every claim to carry a source and date, **so that** I can trace and trust each fact.
   - *Example:* "Global AI-art market ~$X in 2024 [SourceA, 2024-11]" — no orphan facts.
4. **As a downstream reader,** I want conflicting sources shown side by side, **so that** I see the disagreement instead of an arbitrary pick.
   - *Example:* SourceA says 40% adoption (2023), SourceB says 55% (2025) — both shown with attribution and dates, temporal difference noted.
5. **As a research requester,** I want a usable report even when a source is unavailable, **so that** one failure doesn't sink the whole briefing.
   - *Example:* The "music" subagent's endpoint times out → the report ships the other three facets and annotates "music: gap — source unavailable."
6. **As a builder,** I want the coordinator to spawn subagents in parallel, **so that** a multi-subtopic query returns measurably faster than sequential.
   - *Example:* A 3-subtopic query issues three `Task` calls in one response; wall-clock ≈ slowest subagent, not the sum.
7. **As a builder,** I want narrow queries to skip the full pipeline, **so that** I don't pay 15× cost for a simple lookup.
   - *Example:* "What year was Stable Diffusion released?" → single-agent fallback, no fan-out.
8. **As an architecture reviewer,** I want a written justification and token metrics, **so that** I can confirm multi-agent was the right architecture and know when a single agent suffices.

## 6. Core Architecture & Patterns

**Topology (hub-and-spoke, TR1).** One `coordinator` is the hub. It decomposes, delegates, aggregates, and handles errors. Subagents are spokes that communicate *only* with the coordinator — never peer-to-peer. Aggregation happens exclusively in the coordinator.

```
                         ┌─────────────┐
          question ─────▶│ COORDINATOR │──────▶ cited report
                         └─────────────┘
              decompose ▲  │ Task×N (parallel)  ▲ distilled summaries
                        │  ▼                     │
        ┌──────────┬────┴──────┬───────────┬─────┴─────┐
        ▼          ▼           ▼           ▼           ▼
   web_search  web_search  doc_analysis  synthesis   report
   (facet A)   (facet B)   (facet C)
```

**Proposed directory structure** (mirrors the sibling `customer-support` project):

```
src/
  coordinator.py       # decomposition, dynamic selection, parallel Task dispatch, refinement loop, aggregation
  agents/              # subagent definitions (system prompts, allowed_tools, model tier)
    web_search.py
    doc_analysis.py
    synthesis.py
    report.py
  tools/
    server.py          # MCP tool(s): web_search over the seeded corpus
  mocks/
    corpus.py          # seeded corpus: 4+ facets, conflicting sources, dated source, timeout endpoint
  schemas.py           # structured claim→source, subagent result, error envelope
  errors.py            # failure types + retry classification
run_example.py         # single-question end-to-end entry point
tests/                 # scripted scenario suite (regression gate)
```

**Key patterns:**
- **Explicit context passing (TR2).** Subagents inherit nothing; each `Task` prompt carries the full subtopic, source-type assignment, and output contract.
- **Parallel fan-out (TR2).** Multiple `Task` calls emitted in a *single* coordinator response run concurrently; a coordinator missing `"Task"` in `allowedTools` cannot delegate (demonstrated failure → fix).
- **Dynamic selection (TR3).** A cheap classifier (Haiku-tier) decides fan-out vs. single-agent fallback and which subagents to run.
- **Context isolation (TR6).** Each subagent condenses its exploration to a ~1–2k-token structured summary; the coordinator synthesizes summaries, never raw transcripts.
- **Refinement loop (TR5).** After synthesis, evaluate coverage against the intended facet set; re-delegate targeted queries for gaps; re-synthesize until sufficient (with a bounded iteration cap as a backstop).
- **Structured data everywhere.** Subagent outputs separate content from metadata so provenance survives aggregation.

**Model tiering:** coordinator on **Opus-tier** reasoning; workers (`web_search`, `doc_analysis`, `synthesis`) on **Sonnet**; trivial classification on **Haiku**.

## 7. Tools / Features

### 7.1 Subagents

| Subagent | Purpose | Input (from coordinator) | Output contract |
|---|---|---|---|
| `web_search` | Retrieve sources for one assigned facet from the mocked corpus. | Subtopic, source-type scope, query hints. | Distilled summary + structured claim→source→date mappings (TR6, TR8). |
| `doc_analysis` | Extract claims/figures from a specific document. | Document ref + extraction goal. | Structured claims with excerpts + dates. |
| `synthesis` | Merge subagent summaries into a coherent, cited narrative; preserve conflicts and temporal context. | All subagent summaries + intended facet set. | Draft report sections with per-claim citations + a coverage map. |
| `report` | Render the synthesized result by content type. | Synthesized sections + coverage map. | Final report: tables for figures, prose for analysis, coverage annotations (TR9). |

### 7.2 Tools (MCP)

- **`web_search`** — the single real tool, backed by the mocked seeded corpus. Rich description (purpose, input format, when-to-use). Returns results **and** structured errors (TR7): `isError` with a failure type, `isRetryable`, attempted query echoed back, and any partial results.

### 7.3 Seeded corpus (mock backend)

Engineered so each failure mode is deterministic and reproducible:
- **(a)** A topic with **4+ facets** (exercises decomposition/coverage, TR4).
- **(b)** **Two credible sources that conflict** on a value (exercises conflict handling, TR8).
- **(c)** A source **dated differently** from another (exercises temporal handling, TR8).
- **(d)** An endpoint that **times out** (exercises retry + partial-result propagation, TR7).

## 8. Technology Stack

- **Language:** Python **3.10** (shared monorepo venv at `../../.venv`).
- **Runtime:** `claude-agent-sdk` (coordinator uses `Task` for subagent spawning; `allowed_tools` for least-privilege scoping).
- **Models:** Opus-tier (coordinator), Sonnet (workers), Haiku (classification).
- **Config:** `python-dotenv`; keys from monorepo-root `.env` (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`).
- **Testing:** `pytest` + `pytest-asyncio` (`asyncio_mode = auto`, `integration` marker for real SDK/API calls) — mirror the sibling's `pytest.ini`.
- **Package management:** `pip` into the shared venv (add a `requirements.txt`).
- **Optional / stretch:** an MCP search server for real retrieval; `fork_session` for strategy comparison; an LLM-judge grading harness.

## 9. Security & Configuration

- **Auth:** SDK uses the workspace CLI/API credentials; no per-user auth in scope.
- **Configuration:** env-driven via root `.env`; model tiers and iteration caps as named constants.
- **Least privilege:** each subagent gets only the `allowed_tools` it needs; only the coordinator has `"Task"`.
- **Security scope:** *In* — no secrets in code, deterministic bounds on refinement iterations (runaway-loop backstop). *Out* — network hardening, multi-tenant isolation, deployment.

## 10. API Specification

Not a networked API for the MVP. The public surface is a single entry point:

```python
report = run_research(question: str) -> Report
# Report = { sections: [...], claims: [{claim, source, excerpt, date}], coverage: {facet: status}, gaps: [...] }
```

- **Input:** a natural-language research question.
- **Output:** a structured `Report` object (sections, claims with citations, coverage map, gap annotations) plus token-usage metrics.

## 11. Success Criteria

**MVP is successful when** a broad question yields a fully-cited, full-coverage report that degrades gracefully and justifies its cost. Validation asserts on **structure**, never prose.

- ✅ A coordinator without `"Task"` in `allowedTools` cannot delegate — failure demonstrated, then fixed.
- ✅ Parallel spawning **measurably beats** sequential on a 3-subtopic query (report wall-clock).
- ✅ A broad topic produces coverage across **all major facets** — no whole-subtopic omissions.
- ✅ A simulated subagent **timeout** yields a usable report with the gap annotated (no abort, no silent empty).
- ✅ **Two conflicting sources both appear** with attribution and dates; no arbitrary pick.
- ✅ **100% of report claims carry a source** — no orphan facts.
- ✅ A short **written justification** for multi-agent (and when a single agent is preferable) exists.
- ✅ **Token usage is tracked** to make the ~15× cost concrete.

**Quality indicators:** simple queries take the single-agent fallback; refinement closes an injected coverage gap; conflicting values are annotated, not silently merged.

## 12. Implementation Phases (PIV)

### Phase 1 — Spine
- **Goal:** Coordinator + two subagents (`web_search`, `doc_analysis`) with explicit context passing and a single synthesis pass.
- **Deliverables:** ✅ `requirements.txt` + SDK installed · ✅ coordinator with `"Task"` · ✅ two subagents receiving context via prompt · ✅ `web_search` MCP tool over a minimal seeded corpus · ✅ one synthesis pass → basic report · ✅ `run_example.py`.
- **Validate:** `Task` works; subagents get their context; a basic report is produced; the no-`Task` failure is demonstrable.

### Phase 2 — Parallel + Dynamic
- **Goal:** Parallel `Task` spawning + dynamic subagent selection.
- **Deliverables:** ✅ multiple `Task` calls in one response · ✅ Haiku-tier classifier for fan-out vs. single-agent fallback.
- **Validate:** measured latency drop vs. sequential on a 3-subtopic query; simple queries skip unneeded subagents.

### Phase 3 — Coverage + Refinement
- **Goal:** Scope partitioning + iterative refinement loop.
- **Deliverables:** ✅ facet partitioning across subagents · ✅ coverage evaluation vs. intended facet set · ✅ gap-triggered re-delegation + re-synthesis (bounded).
- **Validate:** full-topic coverage; an injected gap triggers re-delegation; the "only-one-facet" failure is gone.

### Phase 4 — Reliability + Provenance
- **Goal:** Structured error propagation, claim→source mappings, conflict/temporal handling, coverage annotations.
- **Deliverables:** ✅ error envelope (type, attempted query, partials, alternatives) + access-failure vs. valid-empty distinction + local retry · ✅ claim→source→date schema preserved through synthesis · ✅ conflict + temporal annotation · ✅ coverage annotations rendered by content type.
- **Validate:** a timeout yields a partial annotated report; conflicts preserved with sources; every claim cited.

## 13. Future Considerations

- Real search via an **MCP server** replacing the mocked corpus.
- **Crash-recovery** using structured state manifests the coordinator reloads on resume (D5.4).
- **`fork_session`** to compare two decomposition strategies from a shared baseline (D1.7).
- An **LLM-judge grading rubric** scoring reports for coverage and citation completeness.
- Streaming progress / partial-report rendering as subagents return.

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Narrow decomposition** — coordinator covers only one facet. | Misleading, incomplete briefing (the canonical failure). | Explicit facet partitioning (TR4) + a coverage-evaluation refinement loop (TR5) asserting against known facets in tests. |
| **Lost provenance** — claims arrive without sources after aggregation. | Untrustworthy report; orphan facts. | Structured claim→source→date schema end-to-end (TR8); test asserts 100% of claims carry a source. |
| **Swallowed errors** — a subagent failure aborts the run or returns a silent empty. | Whole briefing lost, or a gap read as "nothing found." | Structured error envelope distinguishing access-failure vs. valid-empty; local retry then annotate-and-continue (TR7). |
| **Runaway cost / refinement loop** — fan-out or re-delegation without bound. | 15× cost balloons; possible infinite loop. | Dynamic selection + single-agent fallback (TR3/TR10); bounded refinement iterations as a backstop; token tracking. |
| **Context bleed** — coordinator drowns in raw subagent transcripts. | Blown context window; degraded synthesis. | Context isolation — subagents return ~1–2k-token distilled summaries only (TR6). |
| **Conflicts silently resolved** — model picks one of two credible sources. | Hidden disagreement, false confidence. | Conflict-annotation contract in synthesis + a seeded conflicting-source pair asserted in tests (TR8). |

## 15. Appendix

**Related documents**
- Spec (source of truth): [`02-multi-agent-research-system.md`](./02-multi-agent-research-system.md)
- Sibling reference implementation: `../../customer-support/` (Agent SDK loop, MCP tools, hooks, scripted scenario suite)
- Project guidance: [`../CLAUDE.md`](../CLAUDE.md)

**Read first (from the spec)**
- "How we built our multi-agent research system" (Anthropic)
- "Effective context engineering for AI agents" (Anthropic)
- Agent SDK — [Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents) & [Sessions](https://platform.claude.com/docs/en/agent-sdk/sessions)

**CCA-F coverage**

| Task statement | Exercised by |
|---|---|
| D1.2 Coordinator–subagent orchestration | TR1, TR3, TR4, TR5 |
| D1.3 Subagent invocation, context passing, parallel spawning | TR2 |
| D1.7 Session forking (stretch) | Architecture |
| D2.2 Structured errors / partial results | TR7 |
| D5.3 Error propagation across agents | TR7, TR9 |
| D5.4 Context in large exploration (isolation, manifests) | TR6, stretch |
| D5.6 Provenance, conflict, temporal handling | TR8, TR9 |
