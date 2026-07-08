"""Offline tests for the prior-findings store (TR8/FR3 persistence).

Always uses ``base_dir=tmp_path`` so the real ``config.PRIOR_FINDINGS_DIR`` is
never written — a test that polluted the repo store would leak state across
runs and break determinism.
"""

import store
from parse import Finding, Location


def _f(file, line, pattern="none-deref"):
    return Finding(
        location=Location(file, line),
        issue="x",
        severity="high",
        suggested_fix="fix",
        detected_pattern=pattern,
        category="correctness",
    )


def test_round_trip_loss_free(tmp_path):
    findings = [
        _f("src/orders.py", 24, "none-deref"),
        _f("src/summary.py", 14, "cross-file-key-mismatch"),
    ]
    store.save_findings("pr", findings, base_dir=tmp_path)
    loaded = store.load_prior("pr", base_dir=tmp_path)
    assert loaded == findings  # dataclass == is field-wise incl. nested Location


def test_load_missing_pr_id_returns_empty(tmp_path):
    assert store.load_prior("never-saved", base_dir=tmp_path) == []


def test_save_creates_dir(tmp_path):
    target = tmp_path / "nested" / "dir"
    assert not target.exists()
    path = store.save_findings("pr", [_f("src/orders.py", 24)], base_dir=target)
    assert path.exists()
    assert path.parent == target


def test_pr_id_from_diff_path():
    assert store._pr_id("fixtures/sample-repo/pr.diff") == "pr"
    assert store._pr_id("/abs/path/pr-02.diff") == "pr-02"
    assert store._pr_id("weird name!.diff") == "weird-name"


def test_finding_dict_helpers_are_inverse():
    f = _f("src/orders.py", 24, "none-deref")
    assert store.finding_from_dict(store.finding_to_dict(f)) == f
