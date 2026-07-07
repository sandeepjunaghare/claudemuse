"""Offline tests for the CLI entrypoint's failure handling (TR1). No CLI call.

These monkeypatch ``runner.invoke_claude`` so the edge cases run without shelling
out: a timeout must surface as a clean exit-1 (never a hang), and a CLI error
envelope must surface as exit-1 with the raw output preserved.
"""

import subprocess

import cli
import runner
from runner import RunResult


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
