"""Structural duplicate suppression for findings (TR8/FR3).

Pure, total, deterministic, stdlib-only — never raises, never touches the CLI,
network, or filesystem, and unit-tests offline with no credentials.

This is the **deterministic backstop** of the two-layer dedupe design (mirrors
the Phase-2 severity two-layer pattern):

1. **Structural (here):** collapse duplicate findings *within* a run (the
   per-file / integration-pass overlap) and, on a re-run, suppress findings
   already reported in a prior run — matched by file + ``detected_pattern`` +
   line-within-tolerance. This is the guarantee behind "a second commit produces
   zero duplicate comments."
2. **Prompt-context (implemented in ``cli.py`` / ``multipass.py``):** prior
   findings are rendered by ``render_prior_findings`` here and injected into the
   ``{prior_findings}`` slot of the enriched + integration review prompts, so the
   model itself reports only new / still-unresolved issues — catching semantic
   dupes when line numbers drift beyond the structural tolerance (and resolving
   the cross-end drift where the same cross-file bug is reportable at the
   producer OR consumer file). The structural layer remains the deterministic
   backstop; the two are belt-and-suspenders.

Identity is ``detected_pattern`` (our controlled slug), NEVER ``issue`` prose —
the model rewords prose every run, so matching on it would make dedupe
nondeterministic. Callers apply ``severity.apply_canonical_severity`` *before*
dedupe so severity is never part of the identity either (a relabeled severity
must not make an already-reported finding look "new").
"""

from parse import Finding


def _same_file(a: str, b: str) -> bool:
    """Suffix-tolerant path match (copied verbatim from ``metrics._same_file``).

    The model may report ``orders.py`` for ``src/orders.py`` (staged-relative vs
    ground-truth-relative). Replicated here so ``dedupe`` stays self-contained
    and pure — not worth a shared util module for one 3-liner.
    """
    a = (a or "").replace("\\", "/").lstrip("./")
    b = (b or "").replace("\\", "/").lstrip("./")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def is_duplicate(a: Finding, b: Finding, tolerance: int) -> bool:
    """True iff ``a`` and ``b`` are the same issue for dedupe purposes.

    Same file (suffix-tolerant) AND line within ``tolerance`` AND same
    ``detected_pattern`` (exact slug match — our controlled vocabulary). If
    *either* pattern is empty, fall back to file + line-within-tolerance only —
    avoids collapsing unrelated unslugged findings that merely share a pattern-
    less blank. Never raises.
    """
    if not _same_file(a.location.file, b.location.file):
        return False
    if abs(a.location.line - b.location.line) > tolerance:
        return False
    pat_a = (a.detected_pattern or "").strip()
    pat_b = (b.detected_pattern or "").strip()
    if pat_a and pat_b:
        return pat_a == pat_b
    # Empty pattern on either side → identity is file + line only (already
    # satisfied above). This intentionally collapses two blank-pattern findings
    # at the same location, but never two DIFFERENT slugs.
    return True


def dedupe(findings: "list[Finding]", *, tolerance: int) -> "list[Finding]":
    """Collapse duplicate findings within a list, keeping the FIRST occurrence.

    Handles the per-file / integration-pass overlap. Stable and keep-first:
    callers may order the list so a higher-value pass (e.g. the integration
    pass) is placed first, but this function does not depend on that. Pure —
    returns a new list, never mutates the inputs.
    """
    kept: "list[Finding]" = []
    for f in findings:
        if any(is_duplicate(f, k, tolerance) for k in kept):
            continue
        kept.append(f)
    return kept


def suppress_prior(
    findings: "list[Finding]",
    prior: "list[Finding]",
    *,
    tolerance: int,
) -> "tuple[list[Finding], list[Finding]]":
    """Split ``findings`` into ``(new, still_unresolved)`` against a prior run.

    * ``new`` — findings NOT matching any ``prior`` finding: the genuinely
      new/first-time issues to comment on.
    * ``still_unresolved`` — findings that DID match a prior one: already
      reported, so **not** re-commented, but returned so callers can report
      "N still-unresolved".

    This is the TR8/FR3 core: a re-run whose issues were all reported before
    yields an EMPTY ``new`` list → zero duplicate comments. Pure, never raises,
    never mutates inputs.
    """
    new: "list[Finding]" = []
    still: "list[Finding]" = []
    for f in findings:
        if any(is_duplicate(f, p, tolerance) for p in prior):
            still.append(f)
        else:
            new.append(f)
    return new, still


#: Neutral first-run marker so the ``{prior_findings}`` prompt slot always
#: resolves (no leftover token) and, when empty, does not change model behavior.
_NO_PRIOR_SENTINEL = "(none — this is the first review of this PR)"


def render_prior_findings(prior: "list[Finding]") -> str:
    """Render prior findings as prompt text the model reads to know what NOT to
    repeat (the prompt-context dedupe layer).

    Empty ``prior`` → a neutral sentinel (first-run behavior unchanged).
    Non-empty → a stable, deterministically-sorted (by file, then line) bullet
    list ``- {file}:{line} [{detected_pattern}] {issue}``. Sorting never relies
    on input order so the composed prompt is stable across runs — a wobbling
    prompt would make the semantic layer nondeterministic. Pure, stdlib-only,
    never raises.
    """
    if not prior:
        return _NO_PRIOR_SENTINEL
    ordered = sorted(prior, key=lambda f: (f.location.file, f.location.line))
    return "\n".join(
        f"- {f.location.file}:{f.location.line} "
        f"[{(f.detected_pattern or '').strip()}] {f.issue}"
        for f in ordered
    )
