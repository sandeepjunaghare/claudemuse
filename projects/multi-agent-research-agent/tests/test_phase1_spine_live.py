"""Phase 1 integration tests: the hub-and-spoke spine, end-to-end (live API).

Ground truth is STRUCTURE — which subagents were delegated to, how the run terminated,
whether the report carries citations — never the model's wording. Each test costs real
API calls (~1 Opus coordinator + Sonnet subagents), so they run only under
`-m integration` and skip cleanly when no credentials/CLI are present.
"""

import shutil

import pytest

import config

# The Agent SDK runs the `claude` CLI subprocess, which authenticates via the user's
# Claude Code login OR ANTHROPIC_API_KEY. Skip only if neither exists (mirrors sibling).
_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _runnable,
        reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run.",
    ),
]

_QUESTION = "What is the impact of AI on creative industries?"

# Facet keywords used only as a LENIENT breadth signal — not a phrasing assertion.
_FACET_KEYWORDS = ["art", "music", "writ", "film"]


@pytest.mark.asyncio
async def test_coordinator_delegates_to_subagents(run_research):
    """TR1/TR2: the coordinator fans out to specialist subagents and finishes cleanly."""
    run = await run_research(_QUESTION)

    # Delegation actually happened, only to the registered subagents.
    assert len(run.delegations) >= 2, run.delegations
    assert run.delegated_subagents <= {"web_search", "doc_analysis"}, run.delegated_subagents
    # Both specialists are exercised (the system prompt directs using each at least once).
    assert "web_search" in run.delegated_subagents, run.delegated_subagents
    assert "doc_analysis" in run.delegated_subagents, run.delegated_subagents

    # Terminal outcome (TR1): finished on a successful ResultMessage, not the cap.
    assert run.terminated_by_result is True
    assert run.terminated_by_cap is False, run.subtype
    assert run.subtype == "success", run.subtype

    # A non-empty report spanning more than one facet (lenient breadth signal).
    assert run.final_text.strip()
    hits = sum(1 for k in _FACET_KEYWORDS if k in run.final_text.lower())
    assert hits >= 2, (hits, run.final_text[:400])
    # Guard against the "I've launched agents, will report back" false positive: a real
    # synthesized briefing carries at least one bracketed citation, an announcement does not.
    assert "[" in run.final_text and "]" in run.final_text, run.final_text[:400]


@pytest.mark.asyncio
async def test_report_carries_citations(run_research):
    """FR5 (lenient Phase-1 signal): the report shows bracketed source/date markers.

    The full structural 100%-citation assertion lands in Phase 4; here we only confirm
    provenance survived to the report at all, via the `[source, date]` shape.
    """
    run = await run_research(_QUESTION)
    text = run.final_text
    assert "[" in text and "]" in text, text[:400]
    # At least one real corpus date should have propagated through synthesis.
    assert any(year in text for year in ("2023", "2024", "2025")), text[:400]


@pytest.mark.asyncio
async def test_no_delegation_config_cannot_fan_out(run_no_delegation):
    """Negative / acceptance demo: `tools=[]` coordinator demonstrably cannot delegate.

    It may still answer from its own knowledge — the point is that NO delegation block
    (`Agent`/`Task`) can appear, proving the topology depends on the delegation tool (TR2).
    """
    run = await run_no_delegation(_QUESTION)
    assert run.delegations == [], run.delegations
    assert "Agent" not in run.tool_calls
    assert "Task" not in run.tool_calls
    assert run.terminated_by_result is True
