"""Project configuration: model tiers, pipeline constants, and `.env` loading.

Unlike the Agent-SDK siblings, this project uses the plain `anthropic` SDK, so the
API key is a hard prerequisite for any live call — there is no `claude` CLI auth
fallback. The `.env` lives at the **workspace root** (three levels above this file:
`src/config.py` -> project -> `projects/` -> monorepo root), so the path is computed
from `__file__` rather than assuming the current working directory.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Model tiers (bare IDs, no date suffix; see the claude-api reference) ---

#: Sonnet-tier is the accuracy/cost sweet spot for structured `tool_use` extraction.
EXTRACTION_MODEL = "claude-sonnet-4-6"
#: Haiku-tier for cheap document-type routing.
ROUTER_MODEL = "claude-haiku-4-5"
#: Opus-tier escalation for the hardest layouts, only if calibration shows it pays.
ESCALATION_MODEL = "claude-opus-4-8"

# --- Pipeline constants ---

#: Cap on validation-retry attempts (runaway-loop backstop — TR4).
MAX_RETRY_ATTEMPTS = 3
#: Output token ceiling for a single structured extraction (well under SDK timeout).
EXTRACTION_MAX_TOKENS = 4096
#: Default field-confidence floor below which a document routes to human review (TR8).
DEFAULT_CONFIDENCE_THRESHOLD = 0.7
#: Seconds between Batch API poll attempts.
BATCH_POLL_INTERVAL_SECONDS = 30
#: Max documents per batch request chunk (Batch API allows far more; kept small for recovery).
BATCH_CHUNK_SIZE = 100

# --- Env loading ---

_WORKSPACE_ENV = Path(__file__).resolve().parents[3] / ".env"
_loaded = False


def load_env() -> None:
    """Load the workspace-root `.env` once (idempotent)."""
    global _loaded
    if _loaded:
        return
    load_dotenv(dotenv_path=_WORKSPACE_ENV)
    _loaded = True


def anthropic_key_present() -> bool:
    """True if an Anthropic API key is available after `load_env()`."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_client():
    """Construct an `anthropic.Anthropic` client (lazy import so pure modules stay offline).

    Reads `ANTHROPIC_API_KEY` from the environment (populated by `load_env()`).
    """
    load_env()
    import anthropic

    return anthropic.Anthropic()
