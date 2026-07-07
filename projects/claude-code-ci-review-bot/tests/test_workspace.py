"""Offline unit tests for workspace staging (TR3 isolation + answer-key guard).

The critical invariant: the answer key (``ground_truth.json``) and eval artifacts
(``*.diff``) must NEVER be staged into the model's workspace. A failure here is a
correctness bug (the model could read the answers), not a flake.
"""

import os
import tempfile
from pathlib import Path

import config
import workspace


def test_staging_includes_claude_md_excludes_answer_key():
    d = workspace.stage_workspace(config.FIXTURE_REPO, include_claude_md=True)
    try:
        files = set(os.listdir(d))
        assert (d / "CLAUDE.md").exists()
        assert "ground_truth.json" not in files
        assert not any(name.endswith(".diff") for name in files)
        # source tree is copied
        assert (d / "src").is_dir()
        assert (d / "src" / "orders.py").exists()
    finally:
        workspace.cleanup_workspace(d)


def test_absent_arm_omits_claude_md():
    d = workspace.stage_workspace(config.FIXTURE_REPO, include_claude_md=False)
    try:
        assert not (d / "CLAUDE.md").exists()
        # but source is still there — the only delta is CLAUDE.md
        assert (d / "src" / "orders.py").exists()
    finally:
        workspace.cleanup_workspace(d)


def test_staged_dir_is_under_temp():
    d = workspace.stage_workspace(config.FIXTURE_REPO, include_claude_md=True)
    try:
        temp_root = Path(tempfile.gettempdir()).resolve()
        assert temp_root in d.resolve().parents
    finally:
        workspace.cleanup_workspace(d)


def test_cleanup_removes_and_refuses_non_temp():
    d = workspace.stage_workspace(config.FIXTURE_REPO, include_claude_md=True)
    assert d.exists()
    workspace.cleanup_workspace(d)
    assert not d.exists()

    # Footgun guard: refuse to remove a path outside the temp dir.
    repo_path = config.FIXTURE_REPO
    assert repo_path.exists()
    workspace.cleanup_workspace(repo_path)
    assert repo_path.exists()  # untouched


def test_staged_context_manager_cleans_up():
    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        captured = ws
        assert ws.exists()
        assert (ws / "CLAUDE.md").exists()
    assert not captured.exists()  # removed on exit
