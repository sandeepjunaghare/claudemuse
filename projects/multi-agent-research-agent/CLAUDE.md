# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: greenfield (no code yet)

This project is **not started** — the directory holds only the spec (`docs/02-multi-agent-research-system.md`) and `.claude/commands/`, and is **entirely untracked** in the parent `claudemuse` monorepo. The spec is the source of truth for *intent*: a **hub-and-spoke multi-agent research system** built on the **Claude Agent SDK** that decomposes a broad question, dispatches subagents in isolated parallel context windows, and synthesizes a **cited** report. Read the spec before writing anything; its technical requirements (**TR1–TR10**), functional requirements (**FR1–FR5**), and acceptance criteria are non-negotiable contracts, not suggestions.

The sibling project `../customer-support/` is a complete, tested reference for the same stack and conventions (Agent SDK loop, MCP tools, hooks, scripted scenario suite as regression gate) — consult its `CLAUDE.md` and `src/` for house style before building.

## Environment

- Python **3.10** via a **shared virtualenv at the monorepo root**: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv` (this project has no venv of its own). Invoke `../../.venv/bin/python` or activate it.
- API keys live in the **monorepo-root `.env`** (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`) — two levels up from here. Load from there.
- The stack (`claude-agent-sdk`, `pytest`, `pytest-asyncio`, `python-dotenv`) is **not yet installed for this project** — add a `requirements.txt` and `pip install` into the shared venv when starting the build. Match the sibling's `pytest.ini` (`asyncio_mode = auto`, an `integration` marker for tests that make real SDK/API calls).
- Per global instructions: use `pytest`; check for an existing `tests/` dir before adding test files.

## The core design distinctions (what the exam probes — read first)

Multi-agent is only justified by **breadth, parallelism, and context-window pressure** (TR10) — it costs ~15× a chat. The failure modes this build must avoid are specific:

- **Topology (TR1).** A single `coordinator` owns *all* decomposition, delegation, aggregation, and error handling. Subagents talk **only** to the coordinator, never to each other.
- **Spawning & context (TR2).** The coordinator's `allowedTools` must include `"Task"` (a coordinator without it cannot delegate — demonstrate that failure). Subagents **inherit nothing**: pass every needed piece of context explicitly in each subagent prompt. Achieve parallelism by emitting **multiple `Task` calls in one coordinator response**.
- **Context isolation (TR6).** Each subagent explores in its own window and returns a **condensed ~1–2k-token summary**, not its full transcript. Detail stays isolated; the lead synthesizes summaries only.
- **Scope partitioning & coverage (TR4/FR2).** Assign distinct subtopics/source types per subagent to minimize duplicate retrieval, and verify coverage spans the **whole** topic — the canonical failure is covering only one facet (the "only visual arts" trap).
- **Iterative refinement (TR5).** After synthesis, the coordinator evaluates for coverage gaps, re-delegates targeted queries, and re-synthesizes until coverage is sufficient.
- **Structured error propagation (TR7/FR4).** A failing subagent returns failure type, attempted query, partial results, and alternatives. Distinguish an **access failure** (retry candidate) from a **valid empty result**. Recover locally (1–2 retries) before propagating; **never** abort the whole run or silently swallow an error.
- **Provenance (TR8/FR5).** Subagents emit structured claim→source mappings (claim, source URL/name, excerpt, **publication date**). Synthesis preserves and merges them. On conflicting credible sources, **annotate both with attribution and dates** — never arbitrarily pick one; include dates so temporal differences aren't misread as contradictions.
- **Dynamic selection (TR3) & cost discipline (TR10).** Inspect each query and invoke only the subagents needed — a simple lookup must **skip the full pipeline** via a single-agent fallback path.
- **Coverage annotations (TR9).** The report marks well-supported findings vs. gaps from unavailable sources, rendered by content type (tables for figures, prose for analysis).

## Intended architecture (from the spec — no code exists yet)

- Agents: `coordinator`, `web_search`, `doc_analysis`, `synthesis`, `report`. Coordinator on Opus-tier reasoning; workers on Sonnet; trivial classification on Haiku.
- Mock `web_search` with a **seeded corpus** engineered to exercise the requirements: (a) a topic with 4+ facets, (b) two credible sources that **conflict**, (c) a source dated differently, (d) an endpoint that **times out**.
- Keep subagent outputs as **structured data** (content separated from metadata) so synthesis can preserve attribution.
- Stretch: `fork_session` to compare decomposition strategies from a shared baseline; crash-recovery via state manifests the coordinator reloads on resume.

## Validation is ground truth, not prose

Seed the corpus so each failure mode is reproducible, then **assert on structure** — coverage of known facets, presence of citations, partial-result handling — never on the model's wording. Acceptance targets: parallel spawning measurably beats sequential on a 3-subtopic query; a broad topic covers all major facets; a simulated timeout yields a usable, gap-annotated report (no abort, no silent empty); conflicting sources both appear with attribution and dates; **100% of report claims carry a source** (no orphan facts). Track token usage to make the ~15× cost concrete and defend the architecture choice.

## Build order (PIV phases)

1. **Spine.** Coordinator + two subagents (search, analysis), explicit context passing, one synthesis pass. *Validate:* `Task` works; subagents receive context; a basic report is produced.
2. **Parallel + dynamic.** Parallel `Task` spawning; dynamic subagent selection. *Validate:* measured latency drop vs. sequential; simple queries skip unneeded subagents.
3. **Coverage + refinement.** Scope partitioning + the refinement loop. *Validate:* full-topic coverage; gaps trigger re-delegation.
4. **Reliability + provenance.** Structured error propagation, claim→source mappings, conflict/temporal handling, coverage annotations. *Validate:* a timeout yields a partial annotated report; conflicts preserved; every claim cited.

## Workflow

Slash commands under `.claude/commands/` drive the PIV loop: `core_piv_loop/prime` (understand the codebase), `core_piv_loop/plan-feature` (deep plan), `core_piv_loop/execute` (run a plan), `core_piv_loop/prime-tools`, plus `create-prd`, `first-ask-pre-plan`, and `commit`. Per global instructions, present a plan and get approval before non-trivial work.
