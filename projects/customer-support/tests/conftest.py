"""Shared test setup: put `src/` on the path, load env, expose a run harness.

Import strategy (standardized per the plan, Task 9): `src/` is inserted on
`sys.path` here so test modules and source modules can use absolute imports
(`import config`, `from loop import run_turn`, `from tools.server import ...`).
"""

import shutil
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Also expose the tests dir so data-only helpers (e.g. `scenarios`) import flat.
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import config  # noqa: E402  (after sys.path setup)
from context import case_facts  # noqa: E402  (SDK-free; safe without the API)
from hooks import verified_store  # noqa: E402  (SDK-free; safe without the API)
from mocks import fixtures  # noqa: E402  (SDK-free; safe without the API)

config.load_env()


@pytest.fixture(autouse=True)
def _reset_verified_store():
    """Clear the process-global verified-customer store before each test (TR4).

    The store is keyed by session_id but shared across the process, so without
    this reset verified state would leak between cases (live and unit alike).
    """
    verified_store.reset()
    yield
    verified_store.reset()


@pytest.fixture(autouse=True)
def _reset_case_facts():
    """Clear the process-global case-facts store before each test (TR9a).

    Like `verified_store`, the case-facts store is keyed by session_id but shared
    across the process; resetting per test prevents facts from one conversation
    leaking into the next (live and unit alike).
    """
    case_facts.reset()
    yield
    case_facts.reset()


@pytest.fixture(autouse=True)
def _reset_flaky():
    """Make the flaky 503 backend deterministic for the WHOLE suite (TR6).

    Two process-global sources of transient failure exist on `fixtures`:
    (1) the forced-failure countdown (the test seam) and (2) the ~10%
    probabilistic path (`FLAKY_503_ENABLED`). The seam is reset between cases so a
    leftover forced failure can't bleed into the next test. The probabilistic path
    is pinned OFF during the suite (and restored after) so it never randomly fires
    in tests that don't intend a transient: no test relies on the probabilistic
    path — deterministic tool tests force their 503s, and live calibration tests
    force theirs too. The production default (`True`) is untouched in source.
    """
    original = fixtures.FLAKY_503_ENABLED
    fixtures.FLAKY_503_ENABLED = False
    fixtures.reset_flaky()
    yield
    fixtures.reset_flaky()
    fixtures.FLAKY_503_ENABLED = original


def agent_runnable() -> bool:
    """Whether live Agent SDK runs are possible in this environment.

    The Agent SDK drives the `claude` CLI as a subprocess, which authenticates
    via the user's existing Claude Code login OR `ANTHROPIC_API_KEY`. The real
    prerequisite is therefore the CLI being present — not the env var (which is
    empty in this workspace yet live runs still succeed via CLI auth).
    """
    return shutil.which("claude") is not None or config.anthropic_key_present()


@pytest.fixture
def run_agent():
    """Return an async callable that runs one agent turn with the default options."""
    from agent import build_options
    from loop import run_turn

    async def _run(prompt: str):
        return await run_turn(prompt, build_options())

    return _run


@pytest.fixture
def run_conversation():
    """Return an async callable that drives a multi-turn conversation (Phase 4).

    Lazy-imports the SDK-backed driver (like `run_agent`) so the deterministic
    suite (`-m "not integration"`) never imports the Agent SDK at collection time.
    """
    from agent import build_options
    from session import run_conversation as _run_conversation

    async def _run(prompts: list[str]):
        return await _run_conversation(prompts, build_options())

    return _run
