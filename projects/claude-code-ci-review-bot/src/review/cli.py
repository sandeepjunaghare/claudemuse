"""``make ci-review`` entrypoint: invoke → parse → emit (Phase 1).

Flow: read the diff file, read the versioned prompt template
(``config.PROMPT_TEMPLATE``), strip its YAML frontmatter, substitute the diff,
run ``claude -p`` headlessly, parse the structured output, and emit findings
mapped to ``file:line``. Every failure mode (timeout, non-zero exit, empty
stdout, CLI error envelope, unparseable output) surfaces as a clean ``exit 1``
with the raw output preserved — never a hang, never a silent drop.
"""

import argparse
import subprocess
import sys

import config
import parse
import post
import runner
import schema


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


def _compose_prompt(template: str, diff: str) -> str:
    """Substitute the diff into the template.

    Uses ``str.replace`` (not ``str.format``) because diffs contain ``{`` / ``}``
    characters that would break ``format``.
    """
    return template.replace("{diff}", diff)


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
    args = parser.parse_args(argv)

    config.load_env()

    try:
        diff = open(args.diff, encoding="utf-8").read()
    except OSError as exc:
        print(f"error: cannot read diff file {args.diff!r}: {exc}", file=sys.stderr)
        return 1

    template = _strip_frontmatter(config.PROMPT_TEMPLATE.read_text(encoding="utf-8"))
    prompt = _compose_prompt(template, diff)

    try:
        result = runner.invoke_claude(
            prompt,
            schema.as_json_string(),
            args.model,
            config.CLAUDE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        print(
            f"error: claude -p timed out after {config.CLAUDE_TIMEOUT_S}s "
            f"(no-hang backstop tripped): {exc}",
            file=sys.stderr,
        )
        return 1

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

    post.emit(review.findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
