"""Pure coverage evaluator: does the briefing span the whole topic? (TR4/TR5).

The coordinator ends its briefing with a machine-readable ``COVERAGE:`` block declaring
which facets it covered. This module parses that block, maps the coordinator's free-text
facet labels onto the canonical facet vocabulary (`corpus.FACETS`) via a lenient alias
table, and computes the `gaps` — the expected facets it did NOT cover. That gap list is
what drives the refinement loop (TR5) and kills the canonical "only visual arts" failure
(TR4/FR2).

Design (mirrors `triage.py` / `mocks/corpus.py`):
  - SDK-free, stdlib-only, so the unit suite exercises it without credentials.
  - Pure, total, deterministic: same input → same output, never raises.
  - The caller passes `expected_facets` (production: `corpus.FACETS`), so this module has
    no dependency on the corpus — trivially testable in isolation.

A prose-scan FALLBACK protects against a missing/malformed block: if no ``COVERAGE:``
block is found, a report whose prose already mentions every facet is NOT falsely flagged
as under-covered (which would trigger needless, costly refinement).

Alias-table safety note: facet aliases are matched as plain substrings, so bare, common
substrings that collide across facets are deliberately EXCLUDED (the plan flagged the
`"video"`→`film` / "music video" collision; the same care applies to `"art"`, which is a
substring of "artificial"/"recording artists", and `"text"`, a substring of the visual-art
corpus's "text-to-image"). The retained aliases are distinctive enough to map the
coordinator's labels without cross-facet false positives.
"""

from dataclasses import dataclass, field

#: Coverage statuses (string constants — mirrors the status style in `triage.py`/`schemas.py`).
STATUS_COVERED = "covered"
STATUS_PARTIAL = "partial"
STATUS_GAP = "gap"

_STATUSES = (STATUS_COVERED, STATUS_PARTIAL, STATUS_GAP)

#: Canonical facet -> distinctive substrings that map a free-text label to it. Keyed by the
#: values of `corpus.FACETS`. Insertion order matters for `canonical_facet` (first match
#: wins) — `music` precedes `film` so "music video" maps to music, never film.
FACET_ALIASES: dict[str, tuple[str, ...]] = {
    "visual_art": ("visual", "illustrat", "artwork", "image", "painting"),
    "music": ("music", "song", "audio"),
    "writing": ("writ", "author", "publish", "manuscript"),
    "film": ("film", "movie", "cinema"),
}

#: Line that opens the coordinator's coverage block (matched case-insensitively).
_COVERAGE_HEADER = "coverage:"


@dataclass
class CoverageResult:
    """The outcome of evaluating one briefing against the expected facet set."""

    map: dict = field(default_factory=dict)  # canonical facet -> status (declared, or fallback-derived)
    covered: set = field(default_factory=set)  # canonical facets judged covered
    gaps: list = field(default_factory=list)  # expected facets NOT covered, in `expected` order


def canonical_facet(label: str) -> str | None:
    """Map a free-text facet `label` to a canonical facet, or None.

    Lowercases `label` and returns the first canonical facet (in `FACET_ALIASES` insertion
    order) any of whose aliases is a substring of it; else None. Total & deterministic.
    """
    text = label.lower()
    for facet, aliases in FACET_ALIASES.items():
        if any(alias in text for alias in aliases):
            return facet
    return None


def facet_mentioned(facet: str, text: str) -> bool:
    """True if any alias of canonical `facet` appears in `text` (the prose-scan fallback)."""
    aliases = FACET_ALIASES.get(facet, ())
    lowered = text.lower()
    return any(alias in lowered for alias in aliases)


def _normalize_status(raw: str) -> str:
    """Coerce a raw status word to one of the three constants; unknown -> PARTIAL."""
    s = raw.strip().lower()
    return s if s in _STATUSES else STATUS_PARTIAL


def parse_coverage_block(report_text: str) -> dict:
    """Parse a ``COVERAGE:`` block into `{canonical_facet: status}`; `{}` if none.

    Finds the first line equal to ``COVERAGE:`` (case-insensitive, after stripping), then
    consumes subsequent ``- <label>: <status>`` lines until a blank or non-matching line.
    Each label is mapped via `canonical_facet` (unmappable labels are ignored); the LAST
    status wins per canonical facet; statuses normalize to the three constants. Total &
    deterministic, never raises.
    """
    lines = report_text.splitlines()
    result: dict = {}
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if stripped.lower() == _COVERAGE_HEADER:
                in_block = True
            continue
        # Inside the block: only ``- <label>: <status>`` lines belong to it.
        if not stripped.startswith("-") or ":" not in stripped:
            break  # blank line or prose ends the block
        body = stripped[1:]  # drop the leading '-'
        label, _, status = body.partition(":")
        facet = canonical_facet(label)
        if facet is not None:
            result[facet] = _normalize_status(status)
    return result


def evaluate(report_text: str, expected_facets: list) -> CoverageResult:
    """Evaluate `report_text`'s coverage against `expected_facets` (TR4).

    Primary path: parse the declared ``COVERAGE:`` block; a facet counts as covered only
    if it is declared `covered`. Fallback (no block): prose-scan — a facet counts as
    covered if any of its aliases appears anywhere in the report (so a well-covered report
    lacking a clean block is not falsely flagged, avoiding needless refinement).

    `gaps` follows `expected_facets` order. Total & deterministic.
    """
    declared = parse_coverage_block(report_text)
    if declared:
        covered = {f for f in expected_facets if declared.get(f) == STATUS_COVERED}
        coverage_map = dict(declared)
    else:
        covered = {f for f in expected_facets if facet_mentioned(f, report_text)}
        coverage_map = {
            f: (STATUS_COVERED if f in covered else STATUS_GAP) for f in expected_facets
        }
    gaps = [f for f in expected_facets if f not in covered]
    return CoverageResult(map=coverage_map, covered=covered, gaps=gaps)
