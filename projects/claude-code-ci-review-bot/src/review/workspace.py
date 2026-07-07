"""Stage a clean review workspace outside the monorepo (TR3 isolation).

``claude -p`` auto-loads ``CLAUDE.md`` from ``cwd`` and *every ancestor* up to
``/`` (plus ``~/.claude`` and managed policy). Running a review with
``cwd=fixtures/sample-repo`` inside the monorepo would therefore leak THIS repo's
bot-dev ``CLAUDE.md`` ("don't import claude-agent-sdk", etc.) into the review —
the two-CLAUDE.md-conflated failure (PRD Risk #3).

The fix: copy the fixture into a fresh temp dir under ``$TMPDIR`` (outside the
monorepo). Walking up from there finds NO project ``CLAUDE.md`` — only the
constant ``~/.claude`` + managed-policy layers. So the ONLY project-memory
variable between the TR3 arms is the fixture's own ``CLAUDE.md``: a clean A/B.

Two staging invariants, both enforced here:
  * The **answer key** (``ground_truth.json``) and **eval artifacts** (``*.diff``)
    are NEVER copied — the model must never see the answers (defense in depth:
    tools aren't granted in P2, but P3 grants Read).
  * ``cleanup_workspace`` refuses to ``rmtree`` any path outside the system temp
    dir — a footgun guard so a staging bug can't delete repo files.
"""

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

#: Filenames excluded from the staged workspace — the answer key. ``*.diff`` eval
#: artifacts are excluded via a glob pattern in ``stage_workspace``.
STAGE_EXCLUDE = {"ground_truth.json"}

#: Glob patterns never copied into the model's workspace: eval artifacts (the
#: answer key + diffs) and build cruft.
_EXCLUDE_GLOBS = ("*.diff", "ground_truth.json", "__pycache__", "*.pyc")


def stage_workspace(fixture_dir: Path, include_claude_md: bool = True) -> Path:
    """Copy ``fixture_dir`` into a fresh ``$TMPDIR`` workspace, minus eval artifacts.

    Args:
        fixture_dir: The source fixture repo (e.g. ``config.FIXTURE_REPO``).
        include_claude_md: When False, the fixture's ``CLAUDE.md`` is also omitted
            (the "absent" arm of the TR3 A/B). When True, it is staged and
            auto-loaded by ``claude -p`` run with ``cwd`` = the returned dir.

    Returns:
        The staged workspace directory (under ``tempfile.gettempdir()``). Caller
        owns cleanup — prefer the ``staged`` context manager.
    """
    fixture_dir = Path(fixture_dir)
    dest = Path(tempfile.mkdtemp(prefix="ci-review-"))
    # copytree needs the destination NOT to pre-exist; mkdtemp created it, so
    # copy into a child and flatten by pointing copytree at dest via dirs_exist_ok.
    shutil.copytree(
        fixture_dir,
        dest,
        ignore=shutil.ignore_patterns(*_EXCLUDE_GLOBS),
        dirs_exist_ok=True,
    )
    if not include_claude_md:
        claude_md = dest / "CLAUDE.md"
        if claude_md.exists():
            claude_md.unlink()
    return dest


def cleanup_workspace(path: Path) -> None:
    """Remove a staged workspace — but only if it lives under the temp dir.

    The temp-dir guard is a footgun backstop (global rule: never delete without
    care): a staging bug that returned a repo path must not be able to wipe it.
    """
    path = Path(path)
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved = path.resolve()
    except OSError:
        return
    if temp_root not in resolved.parents:
        return  # refuse to rmtree anything outside the system temp dir
    shutil.rmtree(resolved, ignore_errors=True)


@contextmanager
def staged(fixture_dir: Path, include_claude_md: bool = True):
    """Context manager: stage a workspace and always clean it up.

    Yields the staged dir; removes it in ``finally`` so callers can't leak temp
    dirs even if the review raises.
    """
    dest = stage_workspace(fixture_dir, include_claude_md=include_claude_md)
    try:
        yield dest
    finally:
        cleanup_workspace(dest)
