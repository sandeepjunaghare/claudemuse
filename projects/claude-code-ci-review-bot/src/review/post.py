"""Emit findings as inline-comment-shaped output (FR1).

Phase 1 *emits* (prints) findings mapped to ``file:line``; real ``gh`` PR
posting is deliberately out of scope (Phase 4, behind an explicit ``--post``
flag — PRD Risk #6: emit-by-default, posting is opt-in). Nothing here imports or
references ``gh``/GitHub.
"""

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
