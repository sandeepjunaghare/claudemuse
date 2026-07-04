"""Phase 3 integration tests: full-topic coverage + injected-gap refinement (live API).

Ground truth is STRUCTURE — parsed coverage maps, gap lists, iteration counts — never the
model's prose. Two acceptance demos:
  - a BROAD question yields a report spanning ALL 4 canonical facets: `run.gaps == []`
    (TR4 — the "only visual arts" trap is detectable and gone);
  - the PARTIAL coordinator under-covers to 2 facets, and `_run_with_refinement` drives
    `refinement_iterations >= 1` to close the writing/film gap end-to-end (TR5).

Costs real API calls (the injected-gap test runs ≥2 full coordinator turns); runs only
under `-m integration`, skips without credentials/CLI.
"""

import shutil

import pytest

import config
import coverage_eval
import triage
from mocks import corpus

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _runnable,
        reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run.",
    ),
]

_BROAD_QUESTION = "What is the impact of AI on creative industries across visual art, music, writing, and film?"

# Lenient breadth signal — not a phrasing assertion.
_FACET_KEYWORDS = ["art", "music", "writ", "film"]


@pytest.mark.asyncio
async def test_broad_query_covers_all_facets(run_research):
    """TR4: a broad question produces a report spanning all four canonical facets."""
    run = await run_research(_BROAD_QUESTION)

    assert run.route == triage.ROUTE_FAN_OUT, run.route
    assert run.subtype == "success", run.subtype

    # Coverage verified against ground truth (via the run's attached coverage OR a re-eval).
    reeval = coverage_eval.evaluate(run.final_text, corpus.FACETS)
    assert run.gaps == [] or reeval.gaps == [], (run.gaps, reeval.gaps, run.final_text[:600])
    # Every canonical facet is marked covered in the final coverage map.
    for facet in corpus.FACETS:
        assert run.coverage.get(facet) == coverage_eval.STATUS_COVERED, (facet, run.coverage)

    # A real synthesized briefing: spans ≥3 facets, carries a citation bracket and a corpus year.
    assert run.final_text.strip()
    hits = sum(1 for k in _FACET_KEYWORDS if k in run.final_text.lower())
    assert hits >= 3, (hits, run.final_text[:400])
    assert "[" in run.final_text and "]" in run.final_text, run.final_text[:400]
    assert any(y in run.final_text for y in ("2023", "2024", "2025")), run.final_text[:400]


@pytest.mark.asyncio
async def test_injected_gap_triggers_refinement(run_partial_then_refine):
    """TR5 acceptance demo: the partial coordinator's gap is closed by refinement, live."""
    run = await run_partial_then_refine(_BROAD_QUESTION)

    # Refinement actually ran — the first pass under-covered.
    assert run.refinement_iterations >= 1, (run.refinement_iterations, run.coverage_history)
    assert len(run.coverage_history) >= 2, run.coverage_history

    # The FIRST pass was missing writing and/or film (the injected gap).
    first_map = run.coverage_history[0]
    first_covered = {f for f, s in first_map.items() if s == coverage_eval.STATUS_COVERED}
    assert {"writing", "film"} - first_covered, first_map  # at least one was not covered initially

    # After refinement the gap is closed (or at least strictly smaller than the first pass).
    final_covered = {f for f, s in run.coverage.items() if s == coverage_eval.STATUS_COVERED}
    assert run.gaps == [] or len(final_covered) > len(first_covered), (run.coverage, first_map)

    # The completed briefing now mentions the previously-missing facets.
    lowered = run.final_text.lower()
    assert coverage_eval.facet_mentioned("writing", lowered)
    assert coverage_eval.facet_mentioned("film", lowered)
