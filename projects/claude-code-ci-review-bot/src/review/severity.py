"""Severity normalization + canonical consistency (TR5).

Pure, total, deterministic, stdlib-only — never raises, never touches the CLI or
network, and unit-tests offline with no credentials.

TR5 ("the same issue class gets the same severity label across different PRs") is
enforced in **two layers**:

1. **Primary lever — the prompt rubric** (``.claude/commands/review/review-diff.md``):
   each severity level carries a concrete code example so the model *emits*
   consistent labels. That shapes behavior but relies on model consistency.
2. **Backstop — this module's ``PATTERN_SEVERITY`` override.** For every known
   ``detected_pattern`` slug we assert the canonical severity, overriding whatever
   the model labeled. This makes "identical severity across PRs" **deterministic**
   rather than hoping the model never wavers — which is what the acceptance gate
   actually requires.

Off-vocabulary model labels are coerced leniently to a safe default (``medium``)
rather than raising, mirroring the sibling ``coverage_eval._normalize_status``.
"""

from dataclasses import replace

from parse import Finding

#: Canonical severity order, highest→lowest. The single source of truth for
#: ranking/sorting (TR5). Mirrors the schema enum in ``schema.FINDINGS_SCHEMA``.
SEVERITY_LEVELS: "tuple[str, ...]" = ("critical", "high", "medium", "low")

_SEVERITY_SET = set(SEVERITY_LEVELS)

#: Likely off-vocabulary words the model might emit → canonical level. Lenient
#: coercion so a stray label never breaks scoring (insertion order irrelevant —
#: exact-key lookup only).
_SEVERITY_ALIASES: "dict[str, str]" = {
    "blocker": "critical",
    "fatal": "critical",
    "error": "high",
    "major": "high",
    "warning": "medium",
    "warn": "medium",
    "moderate": "medium",
    "info": "low",
    "nit": "low",
    "minor": "low",
    "trivial": "low",
}

#: Zero-based rank per level (0 = most severe) for sorting.
SEVERITY_RANK: "dict[str, int]" = {lvl: i for i, lvl in enumerate(SEVERITY_LEVELS)}

#: The TR5 determinism lever: canonical severity per known ``detected_pattern``
#: slug. Keys are OUR controlled slugs (exact match, no substrings) and MUST stay
#: aligned with the slugs the enriched prompt is told to emit. A finding carrying
#: one of these patterns gets this severity regardless of the model's own label.
PATTERN_SEVERITY: "dict[str, str]" = {
    "none-deref": "high",
    "null-deref": "high",
    "key-error": "high",
    "cross-file-key-mismatch": "critical",
    "timing-unsafe-comparison": "high",
    "off-by-one": "medium",
    "unhandled-error-path": "high",
    "resource-leak": "medium",
}

#: Safe default when a label is unknown and unaliased.
DEFAULT_SEVERITY = "medium"


def normalize_severity(raw: str) -> str:
    """Coerce an arbitrary severity label to a canonical level.

    Lowercase/strip → canonical if already in the set → alias table → the safe
    default (``medium``). Never raises.
    """
    s = (raw or "").strip().lower()
    if s in _SEVERITY_SET:
        return s
    return _SEVERITY_ALIASES.get(s, DEFAULT_SEVERITY)


def severity_rank(sev: str) -> int:
    """Return the sort rank (0 = most severe) of a (possibly raw) label."""
    return SEVERITY_RANK[normalize_severity(sev)]


def canonical_severity(finding: Finding) -> str:
    """The authoritative severity for a finding (TR5).

    If ``detected_pattern`` names a known slug, its canonical severity wins
    (overriding the model). Otherwise fall back to normalizing the model's own
    label.
    """
    pattern = (finding.detected_pattern or "").strip().lower()
    if pattern in PATTERN_SEVERITY:
        return PATTERN_SEVERITY[pattern]
    return normalize_severity(finding.severity)


def apply_canonical_severity(findings: "list[Finding]") -> "list[Finding]":
    """Return NEW findings with ``severity`` replaced by the canonical value.

    Pure — uses ``dataclasses.replace``, never mutates the inputs. Idempotent:
    applying twice yields the same result.
    """
    return [replace(f, severity=canonical_severity(f)) for f in findings]


def sort_by_severity(findings: "list[Finding]") -> "list[Finding]":
    """Sort findings most-severe first, then by file/line (stable, readable)."""
    return sorted(
        findings,
        key=lambda f: (
            severity_rank(f.severity),
            f.location.file,
            f.location.line,
        ),
    )
