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

#: Trivial-classification tier (TR3). UNUSED by the Phase-2 deterministic triage
#: (`triage.classify` is a pure function — see triage.py); defined now as the single
#: source of truth for the DEFERRED LLM-classifier seam, so swapping the heuristic for a
#: Haiku call later needs no new constant. Precedent: MAX_REFINEMENT_ITERATIONS below.
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"

# --- Orchestration constants ----------------------------------------------

#: In-process MCP server name; the tool is addressed as ``mcp__research__web_search``.
MCP_SERVER_NAME = "research"

#: Backstop only (TR1): the coordinator loop must terminate on natural completion,
#: never because this cap was hit on a normal run. Asserted in tests.
MAX_TURNS_BACKSTOP = 20

#: Ceiling on the refinement loop (TR5): after synthesis the coordinator may re-delegate
#: for coverage gaps at most this many times. Used by `coordinator._run_with_refinement`.
MAX_REFINEMENT_ITERATIONS = 2

#: Ceiling on a subagent's LOCAL retries of a retryable access failure before it propagates a
#: structured failure to the coordinator (TR7). Referenced in the subagent prompts (the retry is
#: model-driven — "local recovery" happens inside the subagent's own context, which the SDK runs
#: opaquely, so no orchestration code reads this). Named here as the single source of truth;
#: precedent: MAX_REFINEMENT_ITERATIONS above and the deferred CLASSIFIER_MODEL seam.
MAX_TOOL_RETRIES = 2

#: Word-count threshold separating a narrow lookup from a broad question in the Phase-2
#: deterministic triage (TR3). At or below this AND matching a single-fact interrogative
#: → single-agent fallback; above it → parallel fan-out. Read by `triage.classify`.
SIMPLE_QUERY_MAX_WORDS = 12

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
