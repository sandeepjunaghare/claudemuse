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

#: Cheaper tier for ``make metrics`` / integration reviews — caps cost while the
#: A/B arms stay on the SAME tier so the model is never a confound (mirrors the
#: sibling ``CLASSIFIER_MODEL``). ``REVIEW_MODEL`` stays the production default.
BASELINE_MODEL = "claude-haiku-4-5-20251001"

#: Hard timeout (seconds) for a single ``claude -p`` invocation. The backstop that
#: makes "the pipeline never hangs" (TR1) a guarantee rather than a hope.
CLAUDE_TIMEOUT_S = 300

# --- Phase 2: fixture + metrics constants (TR3/TR4/TR5) ---

#: The seeded fixture repo = the ground-truth measurement harness (PRD §6).
FIXTURE_REPO = PROJECT_ROOT / "fixtures" / "sample-repo"

#: The answer key — scored against, NEVER staged into the model's workspace.
GROUND_TRUTH = FIXTURE_REPO / "ground_truth.json"

#: The pre-TR4/TR5 minimal prompt (the "before" arm of the precision metric).
BASELINE_PROMPT = PROJECT_ROOT / ".claude" / "commands" / "review" / "review-diff.baseline.md"

#: The enriched prompt (the "after" arm) — alias of the Phase-1 ``PROMPT_TEMPLATE``.
ENRICHED_PROMPT = PROMPT_TEMPLATE

#: Results store for the before/after precision numbers + TR3 demo.
METRICS_DIR = PROJECT_ROOT / "data" / "metrics"

#: A finding matches a ground-truth case if same file and ``|line - case.line|``
#: is within this tolerance (models report hunk lines ±a few).
LINE_MATCH_TOLERANCE = 3

# --- Phase 3a: multi-pass + dedupe constants (TR6/TR7/TR8/FR3) ---

#: The cross-file integration-pass prompt (TR6). A sibling of the per-file
#: ``review-diff.md``: it sees the WHOLE diff and reports only cross-module /
#: data-flow / contract defects that per-file isolation provably cannot see.
INTEGRATION_PROMPT = PROJECT_ROOT / ".claude" / "commands" / "review" / "review-integration.md"

#: Per-PR prior-findings store for duplicate suppression across re-runs
#: (TR8/FR3). Written on every dedupe-enabled run; distinct store/lifecycle from
#: ``METRICS_DIR`` (only ``make metrics`` writes that) — do NOT conflate them.
PRIOR_FINDINGS_DIR = PROJECT_ROOT / "data" / "prior_findings"

#: Two findings are "the same issue" for structural dedupe if same file + same
#: ``detected_pattern`` and ``|line diff| <= this``. Set equal to
#: ``LINE_MATCH_TOLERANCE`` deliberately — the same "models report hunk lines
#: ±a few" reasoning applies. Line drift *beyond* this tolerance across commits
#: is handled by the prompt-context dedupe layer (prior findings fed to the
#: model to report only new/unresolved), not this structural key — the two-layer
#: design (TR8/FR3).
DEDUPE_LINE_TOLERANCE = 3

# --- Phase 3b: test-generation constants (FR2) ---

#: Versioned test-gen prompt template (FR2). Like ``PROMPT_TEMPLATE``, it is NOT
#: inlined in code or the Makefile; the driver reads this file and substitutes
#: ``{diff}`` + ``{existing_tests}``.
TESTGEN_PROMPT = PROJECT_ROOT / ".claude" / "commands" / "test-gen" / "generate-tests.md"

#: The test-gen ground-truth harness — a SEPARATE fixture from ``FIXTURE_REPO``
#: (whose files carry seeded review bugs and whose CLAUDE.md/metrics are
#: calibrated for the review precision/TR3 A/B). Test-gen needs a *correct*
#: function with an unambiguous untested branch (coverage, not bug-finding).
TESTGEN_REPO = PROJECT_ROOT / "fixtures" / "testgen-sample"

#: The test-gen answer key — scored against, NEVER staged (excluded by the
#: ``*ground_truth.json`` glob in ``workspace.py``).
TESTGEN_GROUND_TRUTH = TESTGEN_REPO / "testgen_ground_truth.json"

#: The change-under-test diff filename inside ``TESTGEN_REPO`` (fed into the
#: prompt, not staged — matches the ``*.diff`` exclusion glob).
TESTGEN_DIFF_NAME = "testgen.diff"

#: The existing-tests file (relative to ``TESTGEN_REPO``) fed into the prompt as
#: the coverage context — the prompt-layer of the two-layer FR2 skip.
TESTGEN_EXISTING_TESTS_NAME = "tests/test_discount.py"

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
