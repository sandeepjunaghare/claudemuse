"""Test configuration: put src/review on the path, load env, gate live tests.

Mirrors the sibling ``multi-agent-research-agent/tests/conftest.py`` pattern,
adjusted because our modules live in ``src/review`` (one level deeper): flat
absolute imports (``import config``, ``from parse import Finding``) work once
``src/review`` is on ``sys.path``.
"""

import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "review"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import config  # noqa: E402

config.load_env()


def claude_runnable() -> bool:
    """True when the ``claude`` CLI is available (gates integration tests)."""
    return shutil.which("claude") is not None


@pytest.fixture
def project_root() -> Path:
    return _ROOT


@pytest.fixture
def sample_output() -> str:
    """The recorded golden CLI stdout, as a string, for offline parse tests."""
    return (_ROOT / "tests" / "fixtures" / "sample_claude_output.json").read_text(
        encoding="utf-8"
    )
