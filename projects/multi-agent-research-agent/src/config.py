"""Project configuration: model tiers, MCP server name, backstop + `.env` loading.

Mirrors the sibling `customer-support/src/config.py`. The `.env` lives at the
**workspace root** (three levels above this file: `src/config.py` -> project ->
`projects/` -> monorepo root), so the path is computed from `__file__` rather than
assuming the current working directory.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Model tiers -----------------------------------------------------------

#: Coordinator (the hub) runs on Opus-tier reasoning — it owns decomposition,
#: delegation, aggregation, and error handling (TR1). `options.model` sets this.
COORDINATOR_MODEL = "claude-opus-4-8"

#: Subagents (web_search, doc_analysis, and later synthesis) run on Sonnet —
#: capable retrieval/extraction workers at lower cost than the coordinator.
WORKER_MODEL = "claude-sonnet-4-6"

# --- Orchestration constants ----------------------------------------------

#: In-process MCP server name; the tool is addressed as ``mcp__research__web_search``.
MCP_SERVER_NAME = "research"

#: Backstop only (TR1): the coordinator loop must terminate on natural completion,
#: never because this cap was hit on a normal run. Asserted in tests.
MAX_TURNS_BACKSTOP = 20

#: Ceiling on the Phase 3 refinement loop (TR5): after synthesis the coordinator may
#: re-delegate for coverage gaps at most this many times. Defined here now as the
#: single source of truth; UNUSED until Phase 3.
MAX_REFINEMENT_ITERATIONS = 2

# --- Env loading -----------------------------------------------------------

#: Workspace-root .env: projects/multi-agent-research-agent/src/config.py -> ../../../.env
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
