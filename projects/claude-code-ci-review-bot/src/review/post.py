"""Emit findings as inline-comment-shaped output (FR1) + optional gh posting.

Default mode *emits* (prints) findings mapped to ``file:line``. Phase 4 adds
real ``gh`` PR posting behind an explicit ``--post`` flag (PRD Risk #6:
emit-by-default, posting is opt-in). ``gh`` is only ever reached as a
``subprocess`` argv on the guarded ``post_via_gh`` path — never imported as a
library; ``--post --dry-run`` prints the exact argv without executing.

Posting uses ``gh pr comment`` (a single summary comment carrying each finding's
``file:line`` in its body), NOT line-anchored review comments: a true inline
review comment needs the PR head commit SHA via ``gh api
repos/{owner}/{repo}/pulls/{n}/comments``, which is not derivable from a bare
diff file. That ``gh api`` variant is a noted extension, not built for the MVP.
"""

import subprocess

from parse import Finding


def format_comment(f: Finding) -> str:
    """Format one finding as a single inline-comment-shaped line + fix detail.

    The ``file:line`` pairing is explicit — this is the "maps to a real comment
    location" acceptance gate.
    """
    return (
        f"{f.location.file}:{f.location.line} [{f.severity}] {f.issue}\n"
        f"    ↳ fix: {f.suggested_fix} "
        f"(pattern={f.detected_pattern}, category={f.category})"
    )


def emit(findings: list) -> None:
    """Print a count header followed by one formatted comment per finding."""
    print(f"{len(findings)} finding(s)")
    for f in findings:
        print(format_comment(f))


# --- gh PR posting (Phase 4, behind --post; opt-in) --------------------------


def format_review_body(findings: "list[Finding]") -> str:
    """Format all findings as a single markdown PR-comment body.

    Header line (``N finding(s)``) then one ``- `` bullet per finding reusing
    ``format_comment`` (so each bullet carries ``file:line [sev] issue`` + fix +
    pattern/category). An empty list yields a neutral "No findings." body.
    """
    if not findings:
        return "No findings."
    lines = [f"{len(findings)} finding(s):", ""]
    lines.extend(f"- {format_comment(f)}" for f in findings)
    return "\n".join(lines)


def build_gh_comment_args(pr, body: str, *, repo: "str | None" = None) -> "list[str]":
    """Build the ``gh pr comment`` argv (pure — no shell-out).

    ``gh pr comment <pr> --body <body> [--repo <repo>]``. ``pr`` accepts a
    number, URL, or branch (stringified). The body is a single argv element —
    subprocess passes it without a shell, so it is NEVER manually escaped.
    """
    args = ["gh", "pr", "comment", str(pr), "--body", body]
    if repo:
        args += ["--repo", repo]
    return args


def post_via_gh(
    findings: "list[Finding]",
    pr,
    *,
    repo: "str | None" = None,
    dry_run: bool = False,
    run=subprocess.run,
) -> int:
    """Post findings to a real PR via ``gh`` (guarded outward action).

    Builds the argv from ``format_review_body``. On ``dry_run`` prints the exact
    argv and returns 0 WITHOUT shelling out. Otherwise invokes ``run`` (injectable
    for tests) and returns its return code. Never raises on a nonzero ``gh`` exit
    — the code is returned so the caller can surface it.
    """
    args = build_gh_comment_args(pr, format_review_body(findings), repo=repo)
    if dry_run:
        print("DRY RUN — would run: " + " ".join(args))
        return 0
    return run(args, check=False).returncode
