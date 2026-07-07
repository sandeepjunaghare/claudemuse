"""Offline tests for the CLI entrypoint's failure handling (TR1). No CLI call.

These monkeypatch ``runner.invoke_claude`` so the edge cases run without shelling
out: a timeout must surface as a clean exit-1 (never a hang), and a CLI error
envelope must surface as exit-1 with the raw output preserved.
"""

import json
import subprocess

import cli
import instrument
import runner
import store
from parse import Finding, Location
from runner import RunResult


def _canned(findings_dicts):
    """A minimal valid CLI event array wrapping ``findings_dicts``."""
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "terminal_reason": "completed",
            "structured_output": {"findings": findings_dicts},
        },
    ]
    return RunResult(stdout=json.dumps(events), stderr="", returncode=0)


_ND = {
    "location": {"file": "src/orders.py", "line": 24},
    "issue": "find_order can return None; order.total derefs None.",
    "severity": "high",
    "suggested_fix": "Guard for None.",
    "detected_pattern": "none-deref",
    "category": "correctness",
}
_PERF = {
    "location": {"file": "src/slow.py", "line": 3},
    "issue": "speculative perf nit",
    "severity": "low",
    "suggested_fix": "maybe cache",
    "detected_pattern": "speculative-perf",
    "category": "performance",
}


def _finding(file, line, pattern, category):
    return Finding(
        location=Location(file, line),
        issue="prior issue",
        severity="high",
        suggested_fix="fix",
        detected_pattern=pattern,
        category=category,
    )


def test_timeout_surfaces_as_clean_exit_1(monkeypatch, tmp_path, capsys):
    diff = tmp_path / "x.diff"
    diff.write_text("@@ -1 +1 @@\n+bad = x == None\n", encoding="utf-8")

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(runner, "invoke_claude", _raise_timeout)
    rc = cli.main(["--diff", str(diff)])
    assert rc == 1
    assert "timed out" in capsys.readouterr().err


def test_error_envelope_surfaces_as_exit_1(monkeypatch, tmp_path, capsys):
    diff = tmp_path / "x.diff"
    diff.write_text("@@ -1 +1 @@\n+bad = x == None\n", encoding="utf-8")

    error_stream = (
        '[{"type":"result","subtype":"error_during_execution",'
        '"is_error":true,"terminal_reason":"error"}]'
    )
    monkeypatch.setattr(
        runner,
        "invoke_claude",
        lambda *a, **k: RunResult(stdout=error_stream, stderr="", returncode=0),
    )
    rc = cli.main(["--diff", str(diff)])
    assert rc == 1
    assert "error envelope" in capsys.readouterr().err


def test_nonzero_returncode_surfaces_as_exit_1(monkeypatch, tmp_path, capsys):
    diff = tmp_path / "x.diff"
    diff.write_text("@@ -1 +1 @@\n+bad = x == None\n", encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "invoke_claude",
        lambda *a, **k: RunResult(stdout="", stderr="boom", returncode=2),
    )
    rc = cli.main(["--diff", str(diff)])
    assert rc == 1
    assert "failed" in capsys.readouterr().err


def test_missing_diff_file_surfaces_as_exit_1(capsys):
    rc = cli.main(["--diff", "/nonexistent/path/to.diff"])
    assert rc == 1
    assert "cannot read diff file" in capsys.readouterr().err


# --- Phase 4: semantic dedupe + quarantine + gh posting ----------------------


def _write_diff(tmp_path):
    diff = tmp_path / "x.diff"
    diff.write_text("@@ -1 +1 @@\n+x = find() \n", encoding="utf-8")
    return str(diff)


def test_prompt_carries_prior_findings_when_pr_id_given(monkeypatch, tmp_path):
    """The semantic dedupe layer: a prior finding's slug reaches the prompt."""
    prior = [_finding("src/orders.py", 24, "none-deref", "correctness")]
    monkeypatch.setattr(store, "load_prior", lambda *a, **k: prior)
    monkeypatch.setattr(store, "save_findings", lambda *a, **k: None)  # no repo write
    monkeypatch.setattr(instrument, "load_store", lambda **k: instrument._default_store())

    captured = {}

    def fake(prompt, schema_json, model, timeout_s, cwd=None):
        captured["prompt"] = prompt
        return _canned([_ND])

    monkeypatch.setattr(runner, "invoke_claude", fake)
    rc = cli.main(["--diff", _write_diff(tmp_path), "--pr-id", "demo"])
    assert rc == 0
    assert "none-deref" in captured["prompt"]  # prior slug injected


def test_quarantine_filters_before_emit(monkeypatch, tmp_path, capsys):
    """A quarantined category is filtered; other categories still emit."""
    store_shape = {
        "patterns": {
            "speculative-perf": {"category": "performance", "emitted": 8, "dismissed": 6},
        },
        "manual_quarantine": [],
    }
    monkeypatch.setattr(instrument, "load_store", lambda **k: store_shape)
    monkeypatch.setattr(runner, "invoke_claude", lambda *a, **k: _canned([_ND, _PERF]))
    rc = cli.main(["--diff", _write_diff(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "src/orders.py:24" in captured.out  # correctness survives
    assert "src/slow.py:3" not in captured.out  # performance filtered
    assert "quarantined categories" in captured.err


def test_default_path_unchanged_when_store_absent(monkeypatch, tmp_path, capsys):
    """Absent runtime store → no quarantine → the finding emits (default path)."""
    monkeypatch.setattr(instrument, "load_store", lambda **k: instrument._default_store())
    monkeypatch.setattr(runner, "invoke_claude", lambda *a, **k: _canned([_PERF]))
    rc = cli.main(["--diff", _write_diff(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "src/slow.py:3" in captured.out  # not filtered
    assert "quarantined categories" not in captured.err


def test_post_requires_pr(capsys):
    rc = cli.main(["--diff", "/whatever.diff", "--post"])
    assert rc == 1
    assert "--pr" in capsys.readouterr().err


def test_post_dry_run_prints_gh_argv(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(instrument, "load_store", lambda **k: instrument._default_store())
    monkeypatch.setattr(runner, "invoke_claude", lambda *a, **k: _canned([_ND]))
    rc = cli.main(["--diff", _write_diff(tmp_path), "--post", "--pr", "42", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    assert "gh pr comment 42" in out
