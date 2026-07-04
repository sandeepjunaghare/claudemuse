"""Shared test setup: put `src/` on the path, load env, expose a run harness.

Import strategy (mirrors the sibling): `src/` is inserted on `sys.path` here so test
modules and source modules use flat absolute imports (`import config`,
`from loop import run_turn`). SDK-backed drivers are imported LAZILY inside fixtures so
the deterministic suite (`-m "not integration"`) never imports the Agent SDK at
collection time.
"""

import shutil
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import config  # noqa: E402  (after sys.path setup)

config.load_env()


def agent_runnable() -> bool:
    """Whether live Agent SDK runs are possible in this environment.

    The Agent SDK drives the `claude` CLI as a subprocess, which authenticates via the
    user's existing Claude Code login OR `ANTHROPIC_API_KEY`. The real prerequisite is
    the CLI being present — not the env var (empty in this workspace, yet live runs
    still succeed via CLI auth).
    """
    return shutil.which("claude") is not None or config.anthropic_key_present()


@pytest.fixture
def run_research():
    """Return an async callable that runs one research turn (lazy SDK import)."""
    from coordinator import run_research as _run_research

    async def _run(question: str):
        return await _run_research(question)

    return _run


@pytest.fixture
def run_no_delegation():
    """Return an async callable that runs the no-delegation coordinator (lazy import).

    Used by the negative/acceptance-demo test: this coordinator cannot fan out.
    """
    from coordinator import build_no_delegation_options
    from loop import run_turn

    async def _run(question: str):
        return await run_turn(question, build_no_delegation_options())

    return _run


@pytest.fixture
def run_partial_then_refine():
    """Return an async callable that drives the refinement loop from the PARTIAL coordinator.

    Used by the Phase-3 injected-gap acceptance demo (TR5): the partial coordinator
    under-covers on turn 1, and `_run_with_refinement` re-delegates the missing facets until
    coverage is complete (or the cap is hit). Lazy SDK import so the deterministic suite is
    unaffected.
    """
    from coordinator import _run_with_refinement, build_partial_coordinator_options
    from mocks import corpus

    async def _run(question: str):
        return await _run_with_refinement(
            question, build_partial_coordinator_options(), corpus.FACETS
        )

    return _run
