"""Phase 2 integration tests: parallel fan-out + dynamic single-agent fallback (live API).

Ground truth is STRUCTURE, never prose. Two acceptance demos:
  - a BROAD question routes to fan-out and its subagent tasks genuinely OVERLAP
    (`peak_concurrent_tasks >= 2`) — the real TR2/FR3 parallelism proof (the coordinator
    fires one `Agent` call per message, so `max_parallel_delegations` stays 1; concurrency
    comes from `background=True` tasks running at once, per the Phase-2 spike);
  - a NARROW lookup routes to the single-agent fallback: no delegation, but `web_search`
    used directly to answer the fact (TR3/TR10 — no ~15× fan-out cost).

Costs real API calls; runs only under `-m integration`, skips without credentials/CLI.
"""

import shutil

import pytest

import config
import triage

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _runnable,
        reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run.",
    ),
]

# Broad, multi-subtopic question — triages to fan_out ("impact", "across").
_BROAD_QUESTION = "What is the impact of AI on creative industries across visual art, music, and film?"
# Narrow single-fact lookup — triages to single_agent. Chosen so the answer lives ONLY in
# the corpus (D003: "over 10 million tracks in 2024"), forcing a real web_search rather than
# a from-memory recall — the point of the TR3/TR10 grounded-fallback demo.
_LOOKUP_QUESTION = "How many AI music tracks were produced in 2024?"

# Facet keywords used only as a LENIENT breadth signal — not a phrasing assertion.
_FACET_KEYWORDS = ["art", "music", "writ", "film"]


@pytest.mark.asyncio
async def test_broad_query_fans_out_in_parallel(run_research):
    """TR2/FR3: a broad question fans out and the subagent tasks run CONCURRENTLY."""
    run = await run_research(_BROAD_QUESTION)

    # Routed to the full pipeline, and delegation happened only to the registered subagents.
    assert run.route == triage.ROUTE_FAN_OUT, run.route
    assert run.delegated_subagents, run.delegations
    assert run.delegated_subagents <= {"web_search", "doc_analysis"}, run.delegated_subagents

    # THE PARALLELISM PROOF: ≥2 subagent tasks were active at the same time (real overlap,
    # not just delegated in one message — which the coordinator never does).
    assert run.peak_concurrent_tasks >= 2, (run.peak_concurrent_tasks, run.task_events)

    # Clean synthesis, not the max_turns cap.
    assert run.terminated_by_result is True
    assert run.terminated_by_cap is False, run.subtype
    assert run.subtype == "success", run.subtype

    # A real synthesized briefing: spans ≥2 facets, carries a citation bracket AND a corpus
    # year — guards the "I've launched agents, will report back" false finish.
    assert run.final_text.strip()
    hits = sum(1 for k in _FACET_KEYWORDS if k in run.final_text.lower())
    assert hits >= 2, (hits, run.final_text[:400])
    assert "[" in run.final_text and "]" in run.final_text, run.final_text[:400]
    assert any(year in run.final_text for year in ("2023", "2024", "2025")), run.final_text[:400]


@pytest.mark.asyncio
async def test_simple_query_uses_single_agent_fallback(run_research):
    """TR3/TR10 acceptance demo: a narrow lookup skips fan-out and answers directly."""
    run = await run_research(_LOOKUP_QUESTION)

    # Routed to the cheap path — and structurally could not delegate.
    assert run.route == triage.ROUTE_SINGLE_AGENT, run.route
    assert run.delegations == [], run.delegations
    assert "Agent" not in run.tool_calls, run.tool_calls
    assert run.peak_concurrent_tasks == 0, run.task_events  # no subagents at all

    # It answered the fact ITSELF using the web_search tool.
    assert "web_search" in run.tool_calls, run.tool_calls
    assert run.subtype == "success", run.subtype
    assert run.final_text.strip()
