"""Deterministic proof of the bounded refinement loop (TR5). No API.

`_run_with_refinement` is the code-orchestrated loop: run a turn, evaluate coverage,
re-delegate on gaps, bounded by `MAX_REFINEMENT_ITERATIONS`. By monkeypatching `run_turn`
to return canned `AgentRun`s with chosen COVERAGE blocks, we prove — without spending a
single API call — that the loop stops on full coverage, iterates on a gap, is hard-bounded
by the cap, and records `coverage_history` correctly. Importing `coordinator` pulls SDK
types but makes no API call (precedent: `test_coordinator_config.py`).
"""

import pytest

import config
import coordinator
from loop import AgentRun
from mocks import corpus

FACETS = corpus.FACETS

_FULL = "Briefing.\nCOVERAGE:\n- visual art: covered\n- music: covered\n- writing: covered\n- film: covered"
_PARTIAL = "Briefing.\nCOVERAGE:\n- visual art: covered\n- music: covered"


def _fake_run_turn(texts):
    """Build an async `run_turn` stand-in that returns a fresh AgentRun per queued text.

    Records call count and each (prompt, options) it was called with. Matches the real
    signature `run_turn(prompt, options)`.
    """
    state = {"calls": 0, "prompts": [], "texts": list(texts)}

    async def fake(prompt, options):
        state["calls"] += 1
        state["prompts"].append(prompt)
        text = state["texts"].pop(0)
        return AgentRun(final_text=text, subtype="success")

    return fake, state


@pytest.mark.asyncio
async def test_full_coverage_on_first_pass_no_refinement(monkeypatch):
    fake, state = _fake_run_turn([_FULL])
    monkeypatch.setattr(coordinator, "run_turn", fake)

    run = await coordinator._run_with_refinement("Q", coordinator.build_coordinator_options(), FACETS)

    assert run.refinement_iterations == 0
    assert run.gaps == []
    assert run.fully_covered is True
    assert len(run.coverage_history) == 1
    assert state["calls"] == 1  # 1 + refinement_iterations


@pytest.mark.asyncio
async def test_gap_then_closed_one_iteration(monkeypatch):
    # Turn 1 under-covers (2 facets), refinement turn 2 completes all 4.
    fake, state = _fake_run_turn([_PARTIAL, _FULL])
    monkeypatch.setattr(coordinator, "run_turn", fake)

    run = await coordinator._run_with_refinement("Q", coordinator.build_partial_coordinator_options(), FACETS)

    assert run.refinement_iterations == 1
    assert run.gaps == []
    assert len(run.coverage_history) == 2
    # The first pass did NOT cover writing/film (the recorded gap); the final map does.
    first_map = run.coverage_history[0]
    assert first_map.get("writing") != "covered"
    assert first_map.get("film") != "covered"
    assert run.coverage_history[1].get("writing") == "covered"
    assert state["calls"] == 2  # 1 initial + 1 refinement


@pytest.mark.asyncio
async def test_persistent_gap_is_bounded_by_cap(monkeypatch):
    # The turn ALWAYS under-covers → loop must stop at MAX_REFINEMENT_ITERATIONS, not spin.
    fake, state = _fake_run_turn([_PARTIAL] * (config.MAX_REFINEMENT_ITERATIONS + 5))
    monkeypatch.setattr(coordinator, "run_turn", fake)

    run = await coordinator._run_with_refinement("Q", coordinator.build_partial_coordinator_options(), FACETS)

    assert run.refinement_iterations == config.MAX_REFINEMENT_ITERATIONS
    assert run.gaps == ["writing", "film"]  # residual gap remains — the report still ships
    assert run.fully_covered is False
    assert len(run.coverage_history) == config.MAX_REFINEMENT_ITERATIONS + 1
    assert state["calls"] == 1 + config.MAX_REFINEMENT_ITERATIONS
