"""Environment + path constants for the CI review bot.

Mirrors the sibling ``multi-agent-research-agent/src/config.py`` house style:
an idempotent ``load_env()`` that reads the monorepo-root ``.env`` once, plus
module-level constants with ``#:`` doc-comments. This project is a
*CLI-driver* (it shells out to ``claude -p``), not an SDK app, so nothing here
imports ``anthropic`` or ``claude-agent-sdk``.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Path walk from this file (audit the count carefully — it is one level deeper
# than the sibling because our modules live in src/review/, not src/):
#   config.py -> review -> src -> project-root -> projects -> claudemuse (root)
#   parents[0]  parents[1] parents[2]  parents[3]   parents[4]
#: Monorepo-root ``.env`` holding ``ANTHROPIC_API_KEY`` (two levels above the project).
_WORKSPACE_ENV = Path(__file__).resolve().parents[4] / ".env"

#: Project root (claude-code-ci-review-bot/), used to locate the versioned prompt.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Versioned review prompt template (TR3/TR4 alignment — the prompt is not inlined
#: in code or workflow YAML; the runner reads this file and composes the prompt).
PROMPT_TEMPLATE = PROJECT_ROOT / ".claude" / "commands" / "review" / "review-diff.md"

#: Production default model for reviews. Overridable via ``--model``; integration
#: tests override to a cheaper tier to cap cost.
REVIEW_MODEL = "claude-sonnet-4-6"

#: Hard timeout (seconds) for a single ``claude -p`` invocation. The backstop that
#: makes "the pipeline never hangs" (TR1) a guarantee rather than a hope.
CLAUDE_TIMEOUT_S = 300

_loaded = False


def load_env() -> None:
    """Load the monorepo-root ``.env`` exactly once (idempotent)."""
    global _loaded
    if not _loaded:
        load_dotenv(_WORKSPACE_ENV)
        _loaded = True


def anthropic_key_present() -> bool:
    """Return True if ``ANTHROPIC_API_KEY`` is set in the environment."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
