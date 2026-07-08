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


@pytest.fixture
def ground_truth() -> dict:
    """The fixture repo's answer key (loaded offline for scorer tests)."""
    import json

    return json.loads(config.GROUND_TRUTH.read_text(encoding="utf-8"))


@pytest.fixture
def sample_findings():
    """A perfect-review finding list matching the fixture's flaggable cases."""
    from parse import Finding, Location

    return [
        Finding(
            location=Location("src/orders.py", 24),
            issue="find_order returns None on a miss; order.total derefs None.",
            severity="high",
            suggested_fix="Guard for None before accessing attributes.",
            detected_pattern="none-deref",
            category="correctness",
        ),
    ]
