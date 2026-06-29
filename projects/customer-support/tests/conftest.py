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

config.load_env()


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
