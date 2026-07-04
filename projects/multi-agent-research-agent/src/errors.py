"""Structured error taxonomy for retrieval failures (TR7). Pure, SDK-free, never raises.

The spine of structured error propagation: a subagent that hits a failing source must be
able to say *which kind* of failure it was, so the coordinator can react correctly. Two
outcomes must never collapse into the same empty string:

  - an ACCESS FAILURE — the endpoint is unreachable (the D004 timeout). RETRYABLE: the
    source might come back, so a subagent retries locally before propagating.
  - a VALID EMPTY result — the corpus genuinely has no such source. NOT retryable: there
    is nothing to retry; report the gap and move on.

`is_retryable()` is the single source of truth for that distinction (deterministic, total,
unknown type → not retryable). `ErrorEnvelope` carries the four things TR7 requires — the
failure type, the attempted query, any partial results, and an alternative — and renders a
machine-readable `ERROR:` block in the same `- key: value` line style as the Phase-3
`COVERAGE:` block, so it rides back to the model in TEXT (the operative surface).

Mirrors the pure-module ethos of `coverage_eval.py` / `triage.py`: stdlib-only, string
constants for the enum, a `@dataclass` payload — so the unit suite exercises it with no
credentials and no network.
"""

from dataclasses import dataclass, field

#: Failure-type constants (string constants — mirrors the status style in `coverage_eval.py`).
FAILURE_ACCESS_TIMEOUT = "access_timeout"  # the endpoint timed out (D004) — retryable
FAILURE_ACCESS = "access_failure"          # a generic non-timeout access error — retryable
FAILURE_VALID_EMPTY = "valid_empty"        # corpus genuinely has no such source — NOT retryable

#: The retryable access failures. `valid_empty` is deliberately excluded — there is nothing
#: to retry when the corpus simply has no match.
_RETRYABLE: frozenset[str] = frozenset({FAILURE_ACCESS_TIMEOUT, FAILURE_ACCESS})


def is_retryable(failure_type: str) -> bool:
    """True iff `failure_type` names a retryable access failure (TR7). Total; unknown → False."""
    return failure_type in _RETRYABLE


@dataclass
class ErrorEnvelope:
    """The structured failure a retrieval returns (TR7): type, attempted query, partial, alternative.

    Content vs. metadata again: `partial` holds any usable result lines gathered before the
    failure (so a failed source never discards good evidence), while the rest is metadata the
    coordinator uses to annotate the gap. `render()` emits it as a `- key: value` `ERROR:`
    block — text is the surface the model actually sees (`structuredContent` is dropped).
    """

    type: str
    attempted_query: str
    is_retryable: bool
    failed_source: str | None = None
    partial: list[str] = field(default_factory=list)
    alternative: str = ""

    def render(self) -> str:
        """Render a machine-readable `ERROR:` block mirroring the `COVERAGE:` line style.

        Emits lowercase `true`/`false` for `retryable` so the value is unambiguous. Only the
        keys that carry information are emitted (`failed_source` / `alternative` are skipped
        when empty), but `type`, `retryable`, and `attempted_query` always appear. Never raises.
        """
        lines = [
            "ERROR:",
            f"- type: {self.type}",
            f"- retryable: {'true' if self.is_retryable else 'false'}",
            f"- attempted_query: {self.attempted_query!r}",
        ]
        if self.failed_source:
            lines.append(f"- failed_source: {self.failed_source}")
        if self.alternative:
            lines.append(f"- alternative: {self.alternative}")
        return "\n".join(lines)
