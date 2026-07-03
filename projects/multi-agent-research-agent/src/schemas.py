"""Structured data contracts — content separated from metadata (TR8 groundwork).

These dataclasses are the spine of provenance: a `Claim` never travels without its
`SourceRef`, and a `SourceRef` always carries a `date`, so aggregation across
subagents cannot silently orphan a fact or lose the temporal context that later
distinguishes a *conflict* from a *stale figure* (TR8, Phase 4).

Phase-1 scope: `SubagentResult` and `Report` are the operative types; `Report.coverage`
and `Report.gaps` are populated by the Phase 3 refinement loop and Phase 4 annotations,
so they default to empty here (staged setup — do not require them yet). Keeping the
full shape now means later phases add behavior without reshaping the data.

SDK-free so it unit-tests without credentials.
"""

from dataclasses import dataclass, field


@dataclass
class SourceRef:
    """Where a claim came from. `date` is the publication/as-of date as a plain ISO
    string (the corpus stores heterogeneous dates as data; no parsing in Phase 1).
    `url` is optional because a mock corpus source may be name-only."""

    name: str
    url: str | None
    excerpt: str
    date: str


@dataclass
class Claim:
    """A single factual assertion bound to its source (never an orphan fact, FR5)."""

    text: str
    source: SourceRef


@dataclass
class SubagentResult:
    """The distilled ~1–2k-token contract a subagent returns (TR6).

    Content (`summary`) is separated from provenance (`claims`) so the coordinator
    synthesizes summaries while preserving each claim's source + date. `status`
    is "ok" in Phase 1; Phase 4 uses it to mark partial/failed retrievals.
    """

    facet: str
    summary: str
    claims: list[Claim]
    status: str = "ok"


@dataclass
class Report:
    """The final briefing. Phase 1 fills `sections` + `claims`; `coverage` and `gaps`
    are staged for Phase 3 (refinement) / Phase 4 (gap annotations)."""

    sections: list[dict]
    claims: list[Claim]
    coverage: dict[str, str] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)

    def all_claims_have_source(self) -> bool:
        """True iff every claim carries a `SourceRef` — the 100%-citation invariant
        (FR5). The structural check the Phase 4 provenance test asserts on; defined
        now so the contract is testable from Phase 1."""
        return all(isinstance(c.source, SourceRef) for c in self.claims)
