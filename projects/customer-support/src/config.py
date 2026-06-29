"""Project configuration: constants + workspace `.env` loading.

The `.env` lives at the **workspace root** (two levels above this project), so the
path is computed from `__file__` rather than assuming the current working directory.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Constants -------------------------------------------------------------

#: Model id for the agent. Use the latest capable Opus (per claude-api skill / memory).
MODEL = "claude-opus-4-8"

#: Backstop only (TR1): the loop must terminate on natural completion, never because
#: this cap was hit on a normal resolution. Asserted in tests.
MAX_TURNS_BACKSTOP = 20

#: In-process MCP server name; tools are addressed as ``mcp__support__<tool>``.
MCP_SERVER_NAME = "support"

#: Refund policy ceiling (TR3). Unused in Phase 1 — defined here so Phase 2's
#: PreToolUse hook imports a single source of truth.
REFUND_POLICY_LIMIT = 500.0

# --- Env loading -----------------------------------------------------------

#: Workspace-root .env: projects/customer-support/src/config.py -> ../../../.env
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
