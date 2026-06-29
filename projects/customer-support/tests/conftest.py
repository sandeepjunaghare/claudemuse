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

import config  # noqa: E402  (after sys.path setup)
from hooks import verified_store  # noqa: E402  (SDK-free; safe without the API)

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
