"""Offline tests for finding emission (FR1) + gh posting. Structural only."""

import os
import shutil

import pytest
from parse import Finding, Location
from post import (
    build_gh_comment_args,
    emit,
    format_comment,
    format_review_body,
    post_via_gh,
)


def _finding() -> Finding:
    return Finding(
        location=Location("src/mod.py", 7),
        issue="boom",
        severity="high",
        suggested_fix="fix it",
        detected_pattern="null-deref",
        category="correctness",
    )


def test_format_comment_contains_file_line_severity_and_fix():
    text = format_comment(_finding())
    assert "src/mod.py:7" in text  # file:line mapping (the acceptance gate)
    assert "[high]" in text
    assert "fix it" in text
    assert "null-deref" in text


def test_emit_prints_count_header_and_one_line_per_finding(capsys):
    emit([_finding(), _finding()])
    out = capsys.readouterr().out
    assert "2 finding(s)" in out
    assert out.count("src/mod.py:7") == 2


def test_emit_zero_findings(capsys):
    emit([])
    out = capsys.readouterr().out
    assert "0 finding(s)" in out


# --- gh posting (Phase 4) ----------------------------------------------------


def _finding_at(file, line, pattern="null-deref") -> Finding:
    return Finding(
        location=Location(file, line),
        issue="boom",
        severity="high",
        suggested_fix="fix it",
        detected_pattern=pattern,
        category="correctness",
    )


def test_format_review_body_contains_each_finding_location():
    body = format_review_body([_finding_at("src/a.py", 7), _finding_at("src/b.py", 42)])
    assert "src/a.py:7" in body
    assert "src/b.py:42" in body
    assert "2 finding(s)" in body


def test_format_review_body_empty_is_no_findings():
    assert format_review_body([]) == "No findings."


def test_build_gh_comment_args_shape():
    body = "the body"
    # without repo
    args = build_gh_comment_args(42, body)
    assert args == ["gh", "pr", "comment", "42", "--body", "the body"]
    # with repo
    args = build_gh_comment_args("https://github.com/o/r/pull/5", body, repo="o/r")
    assert args[:3] == ["gh", "pr", "comment"]
    assert "--repo" in args and args[args.index("--repo") + 1] == "o/r"
    assert args[args.index("--body") + 1] == body


def test_post_via_gh_dry_run_does_not_shell_out(capsys):
    def _boom(*a, **k):  # must never be called on the dry-run path
        raise AssertionError("gh should not run on a dry run")

    rc = post_via_gh([_finding()], 42, dry_run=True, run=_boom)
    assert rc == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_post_via_gh_executes_when_not_dry_run():
    calls = []

    class _Result:
        returncode = 0

    def _fake_run(args, check=False):
        calls.append((args, check))
        return _Result()

    rc = post_via_gh([_finding()], 42, repo="o/r", run=_fake_run)
    assert rc == 0
    assert len(calls) == 1
    argv, _ = calls[0]
    assert argv[:4] == ["gh", "pr", "comment", "42"]
    assert "--repo" in argv


@pytest.mark.integration
@pytest.mark.skipif(
    not (shutil.which("gh") and os.environ.get("CI_REVIEW_LIVE_PR")),
    reason="needs gh CLI + CI_REVIEW_LIVE_PR env var pointing at a real PR",
)
def test_post_via_gh_real_pr():
    """Skip-by-default real post: only runs when gh is present and the operator
    opts in via CI_REVIEW_LIVE_PR. Documents the live path without requiring it."""
    pr = os.environ["CI_REVIEW_LIVE_PR"]
    rc = post_via_gh([_finding()], pr, repo=os.environ.get("CI_REVIEW_LIVE_REPO"))
    assert rc == 0
