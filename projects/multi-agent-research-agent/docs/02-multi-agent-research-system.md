# Project 02 — Multi-Agent Research System

> **Pitch:** Build a coordinator that delegates to specialized subagents (web search, document analysis,
> synthesis, report) and produces a complete, **cited** report — with isolated context, parallelism, error
> propagation, and provenance done right.
> **Primary domains:** D1 Agentic Architecture (the 27% centerpiece) · D2 Tools & MCP · D5 Context & Reliability.
> **Difficulty:** ●●● · **Effort:** 3–5 days · maps to **official Exam Scenario 3**.

## Problem statement

A research team wants on-demand briefings on broad topics ("impact of AI on creative industries"). You build a
**hub-and-spoke multi-agent system**: a lead coordinator decomposes the topic, dispatches subagents that work
in **isolated context windows and in parallel**, then synthesizes a cited report. The system must cover the
*whole* topic (not just one facet), survive a subagent failure, and never lose source attribution.

## Background / why it matters

Multi-agent research is Anthropic's flagship orchestration case and the highest-weight exam domain. It forces
the hard parts: subagents don't inherit context, coordination has real token cost (~15× chat), and the failure
modes (narrow decomposition, lost provenance, swallowed errors) are exactly what the exam probes.

## Goals & non-goals

- **Goals:** correct coordinator–subagent topology; explicit context passing; parallel `Task` spawning;
  dynamic subagent selection; scope partitioning; iterative refinement to close coverage gaps; structured error
  propagation; preserved provenance with conflict/temporal handling; coverage-annotated output.
- **Non-goals:** a real search backend (mock or use one simple search tool); beating SOTA research quality;
  building infra to host anything. Justify the multi-agent cost — don't use it where a single agent suffices.

## Functional requirements

- FR1. Take a research question and return a structured report with sections, claims, and citations.
- FR2. Decompose the topic into subtopics that **cover the whole space**, assigned across subagents without
  heavy duplication.
- FR3. Run independent subagents **in parallel**; aggregate through the coordinator only.
- FR4. When a subagent fails, continue with partial results and mark the gap.
- FR5. Preserve every claim's source and date; flag conflicting values instead of picking one.

## Technical requirements (mapped to CCA-F task statements)

- **TR1 — Topology (D1.2).** A coordinator owns all inter-subagent communication, decomposition, delegation,
  aggregation, and error handling. Subagents talk only to the coordinator.
- **TR2 — Spawning & context (D1.3).** Coordinator `allowedTools` must include `"Task"`. Pass **all** needed
  context explicitly in each subagent prompt (subagents inherit nothing). Spawn parallel subagents by emitting
  **multiple `Task` calls in one coordinator response**.
- **TR3 — Dynamic selection (D1.2).** The coordinator inspects each query and invokes **only** the subagents
  needed (a simple lookup shouldn't run the full pipeline).
- **TR4 — Scope partitioning (D1.2).** Assign distinct subtopics/source types per subagent to minimize
  duplicate retrieval; verify coverage spans the whole topic (guard against the "only visual arts" failure).
- **TR5 — Iterative refinement (D1.2).** After synthesis, the coordinator evaluates for coverage gaps,
  re-delegates targeted queries, and re-invokes synthesis until coverage is sufficient.
- **TR6 — Context isolation (D5.4).** Each subagent explores in its own window and returns a **condensed,
  distilled summary** (~1–2k tokens), not its full transcript. Keep detail isolated; the lead synthesizes summaries.
- **TR7 — Structured error propagation (D5.3 / D2.2).** A failing subagent returns failure type, attempted
  query, partial results, and alternatives. Distinguish an **access failure** (retry decision) from a **valid
  empty result**. Local recovery (1–2 retries) before propagating; never abort the whole run or silently
  suppress.
- **TR8 — Provenance (D5.6).** Subagents output structured claim→source mappings (claim, source URL/name,
  excerpt, **publication date**). Synthesis preserves and merges them. Handle conflicting credible sources by
  annotating both with attribution; include dates so temporal differences aren't misread as contradictions.
- **TR9 — Coverage annotations (D5.3).** The report marks which findings are well-supported vs which areas have
  gaps due to unavailable sources. Render by content type (tables for figures, prose for analysis).
- **TR10 — Cost discipline (D1).** Document why multi-agent is justified here (breadth, parallelism,
  context-window pressure) and include a single-agent fallback path for narrow queries.

## Architecture guidance (references, not code)

- Agents: `coordinator`, `web_search`, `doc_analysis`, `synthesis`, `report`. Coordinator on Opus-tier
  reasoning; workers on Sonnet; trivial classification on Haiku. Mock `web_search` with a seeded corpus that
  includes (a) a topic with 4+ facets, (b) two credible sources that conflict, (c) a source that's dated
  differently, and (d) an endpoint that times out — to exercise TR4/TR7/TR8.
- Use `fork_session` to compare two decomposition strategies from a shared baseline (optional, D1.7).
- Keep subagent outputs as structured data (separating content from metadata) so synthesis can preserve attribution.

## Build phases (PIV)

1. **Spine.** Coordinator + two subagents (search, analysis) with explicit context passing and a single
   synthesis pass. *Validate:* `Task` works; subagents get their context; a basic report is produced.
2. **Parallel + dynamic.** Parallel `Task` spawning; dynamic subagent selection. *Validate:* measured latency
   drop vs sequential; simple queries skip unneeded subagents.
3. **Coverage + refinement.** Scope partitioning + iterative refinement loop. *Validate:* full-topic coverage;
   gaps trigger re-delegation; the "only-one-facet" failure is gone.
4. **Reliability + provenance.** Structured error propagation, claim-source mappings, conflict/temporal
   handling, coverage annotations. *Validate:* a timeout yields a partial, annotated report; conflicts preserved
   with sources; every claim is cited.

## Acceptance criteria

- [ ] Coordinator without `"Task"` in allowedTools cannot delegate (demonstrate the failure + fix).
- [ ] Parallel spawning measurably beats sequential on a 3-subtopic query.
- [ ] A broad topic produces coverage across all major facets (no whole-subtopic omissions).
- [ ] A simulated subagent timeout produces a usable report with the gap annotated (no abort, no silent empty).
- [ ] Two conflicting sources both appear with attribution and dates; no arbitrary pick.
- [ ] 100% of report claims carry a source; no orphan facts.
- [ ] A short written justification for using multi-agent (and when you'd use a single agent instead).

## Validation strategy

Seed the corpus so each failure mode is reproducible, then assert on structure (coverage of known facets,
presence of citations, partial-result handling) as ground truth. Track token usage to make the ~15× cost
concrete and to defend the architecture choice.

## Stretch goals

- Real search via an MCP server. · Crash-recovery using structured state manifests the coordinator reloads on
  resume (D5.4). · A grading rubric + LLM-judge that scores reports for coverage and citation completeness.

## CCA-F coverage

| Task statement | Exercised by |
|---|---|
| D1.2 Coordinator–subagent orchestration | TR1, TR3, TR4, TR5 |
| D1.3 Subagent invocation, context passing, parallel spawning | TR2 |
| D1.7 Session forking (stretch) | Architecture |
| D2.2 Structured errors / partial results | TR7 |
| D5.3 Error propagation across agents | TR7, TR9 |
| D5.4 Context in large exploration (isolation, manifests) | TR6, stretch |
| D5.6 Provenance, conflict, temporal handling | TR8, TR9 |

**Read first:** How we built our multi-agent research system; Effective context engineering for AI agents;
Agent SDK [Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents) & [Sessions](https://platform.claude.com/docs/en/agent-sdk/sessions).
