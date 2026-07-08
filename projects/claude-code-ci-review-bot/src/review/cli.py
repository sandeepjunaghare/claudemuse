"""``make ci-review`` entrypoint: invoke → parse → emit (Phase 1).

Flow: read the diff file, read the versioned prompt template
(``config.PROMPT_TEMPLATE``), strip its YAML frontmatter, substitute the diff,
run ``claude -p`` headlessly, parse the structured output, and emit findings
mapped to ``file:line``. Every failure mode (timeout, non-zero exit, empty
stdout, CLI error envelope, unparseable output) surfaces as a clean ``exit 1``
with the raw output preserved — never a hang, never a silent drop.
"""

import argparse
import contextlib
import subprocess
import sys

import config
import dedupe
import instrument
import multipass
import parse
import post
import runner
import schema
import severity
import store
import workspace


def _strip_frontmatter(text: str) -> str:
    """Remove a leading ``---`` YAML frontmatter block, if present.

    The prompt template carries frontmatter (``description:``) for use as a
    slash command; the runner wants only the prompt body.
    """
    if text.startswith("---"):
        # Split on the closing '---' of the frontmatter block.
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return text


def _compose_prompt(template: str, diff: str, prior_text: str = "") -> str:
    """Substitute the diff (and any prior findings) into the template.

    Uses ``str.replace`` (not ``str.format``) because diffs contain ``{`` / ``}``
    characters that would break ``format``. ``prior_text`` fills the
    ``{prior_findings}`` slot (the semantic dedupe layer); a template lacking the
    token (e.g. the baseline prompt) makes the replace a harmless no-op.
    """
    return template.replace("{diff}", diff).replace("{prior_findings}", prior_text)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ci-review",
        description="Headless PR-diff review via claude -p; emits structured findings.",
    )
    parser.add_argument(
        "--diff",
        required=True,
        help="Path to a unified diff file (the PR to review).",
    )
    parser.add_argument(
        "--model",
        default=config.REVIEW_MODEL,
        help=f"Model id for claude -p (default: {config.REVIEW_MODEL}).",
    )
    parser.add_argument(
        "--prompt",
        choices=("enriched", "baseline"),
        default="enriched",
        help="Which versioned review prompt to use (default: enriched).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help=(
            "Optional path to the reviewed project. When given, its CLAUDE.md is "
            "staged into a temp workspace and used as cwd so the review gains "
            "project context (TR3)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("single", "multi"),
        default="single",
        help=(
            "single (default) = one whole-diff pass (Phase-1/2 behavior). "
            "multi = per-file passes + a cross-file integration pass (TR6/TR7)."
        ),
    )
    parser.add_argument(
        "--pr-id",
        dest="pr_id",
        default=None,
        help=(
            "Opt-in PR id enabling duplicate suppression across re-runs (TR8/FR3): "
            "prior findings are loaded, already-reported issues are suppressed, and "
            "the current findings are persisted for the next run. Absent = no dedupe."
        ),
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help=(
            "Post findings to a real PR via `gh pr comment` (FR1; opt-in — default "
            "emits to stdout). Requires --pr. Use --dry-run to preview the gh argv."
        ),
    )
    parser.add_argument(
        "--pr",
        default=None,
        help="PR number / URL / branch to post to (required with --post).",
    )
    parser.add_argument(
        "--gh-repo",
        dest="gh_repo",
        default=None,
        help=(
            "Optional OWNER/REPO for `gh pr comment --repo` (the POST target). "
            "Distinct from --repo, which stages a project's CLAUDE.md for TR3."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --post, print the exact gh argv instead of executing it.",
    )
    args = parser.parse_args(argv)

    if args.post and not args.pr:
        print("error: --post requires --pr <number|url|branch>", file=sys.stderr)
        return 1

    config.load_env()

    try:
        diff = open(args.diff, encoding="utf-8").read()
    except OSError as exc:
        print(f"error: cannot read diff file {args.diff!r}: {exc}", file=sys.stderr)
        return 1

    prompt_path = (
        config.BASELINE_PROMPT if args.prompt == "baseline" else config.ENRICHED_PROMPT
    )
    template = _strip_frontmatter(prompt_path.read_text(encoding="utf-8"))

    # TR8 semantic dedupe layer: load prior findings (empty when no --pr-id) and
    # render them into the prompt so the model itself reports only new/unresolved
    # issues. The structural backstop (suppress_prior, below) still runs. An empty
    # prior renders a neutral sentinel, so first-run behavior is unchanged.
    prior = store.load_prior(args.pr_id) if args.pr_id else []
    prior_text = dedupe.render_prior_findings(prior)
    prompt = _compose_prompt(template, diff, prior_text)

    # TR3: when a repo is supplied, stage a clean workspace so claude -p auto-loads
    # exactly that project's CLAUDE.md (and not the bot-dev one). Default (no
    # --repo) preserves Phase-1 behavior: cwd=None, current directory.
    with contextlib.ExitStack() as stack:
        cwd = None
        if args.repo:
            cwd = str(stack.enter_context(workspace.staged(args.repo, True)))

        try:
            if args.mode == "multi":
                # TR6/TR7: N per-file passes + 1 integration pass, each a fresh
                # independent claude -p process. review_multipass already applies
                # canonical severity, within-run dedupe, and severity sort.
                findings = multipass.review_multipass(
                    diff,
                    prompt_path=prompt_path,
                    model=args.model,
                    cwd=cwd,
                    prior_findings=prior,
                )
            else:
                result = runner.invoke_claude(
                    prompt,
                    schema.as_json_string(),
                    args.model,
                    config.CLAUDE_TIMEOUT_S,
                    cwd=cwd,
                )
        except subprocess.TimeoutExpired as exc:
            print(
                f"error: claude -p timed out after {config.CLAUDE_TIMEOUT_S}s "
                f"(no-hang backstop tripped): {exc}",
                file=sys.stderr,
            )
            return 1

    if args.mode == "single":
        if result.returncode != 0 or not result.stdout.strip():
            print(
                f"error: claude -p failed (rc={result.returncode}). "
                f"stderr:\n{result.stderr}\n--- raw stdout ---\n{result.stdout}",
                file=sys.stderr,
            )
            return 1

        try:
            review = parse.parse_result(result.stdout)
        except parse.ParseError as exc:
            print(f"error: could not parse claude output: {exc}", file=sys.stderr)
            return 1

        if review.is_error:
            print(
                f"error: claude reported an error envelope "
                f"(terminal_reason={review.terminal_reason})",
                file=sys.stderr,
            )
            return 1

        # TR5: apply the canonical severity backstop, then sort most-severe-first.
        findings = severity.apply_canonical_severity(review.findings)
        findings = severity.sort_by_severity(findings)

    # TR8/FR3: optional cross-run dedupe (structural backstop to the semantic
    # prompt layer above). When --pr-id is given, suppress issues already reported
    # on a prior run (zero duplicate comments), then persist the ACCUMULATED prior
    # (dedupe(prior + current)) so a previously-reported issue is never forgotten
    # even if the model declined to re-emit it. Absent = no dedupe, no store I/O —
    # byte-for-byte the Phase-1/2 emit path (``prior`` is [] and this block skips).
    if args.pr_id:
        new, still = dedupe.suppress_prior(
            findings, prior, tolerance=config.DEDUPE_LINE_TOLERANCE
        )
        if still:
            print(
                f"({len(still)} still-unresolved finding(s) suppressed as duplicates)",
                file=sys.stderr,
            )
        accumulated = dedupe.dedupe(
            prior + findings, tolerance=config.DEDUPE_LINE_TOLERANCE
        )
        store.save_findings(args.pr_id, accumulated)
        findings = new

    # TR9/FR4: quarantine filter. A category whose dismissal rate crossed the
    # threshold (with enough samples) — or one on the manual override list — is
    # filtered out so it can't poison trust in the rest. Reads the RUNTIME store,
    # which is absent by default → no quarantined categories → a no-op that leaves
    # the default `ci-review` path byte-for-byte unchanged.
    quarantined = instrument.quarantined_categories(
        instrument.load_store(),
        threshold=config.QUARANTINE_RATE_THRESHOLD,
        min_sample=config.QUARANTINE_MIN_SAMPLE,
    )
    findings, dropped = instrument.apply_quarantine(findings, quarantined)
    if dropped:
        print(
            f"({len(dropped)} finding(s) filtered by quarantined categories: "
            f"{', '.join(quarantined)})",
            file=sys.stderr,
        )

    # FR1: emit (default) or post to a real PR via gh (opt-in --post).
    if args.post:
        rc = post.post_via_gh(
            findings, args.pr, repo=args.gh_repo, dry_run=args.dry_run
        )
        if rc != 0:
            print(f"error: gh pr comment failed (rc={rc})", file=sys.stderr)
        return rc

    post.emit(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
