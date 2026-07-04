"""Pure `CLAIMS:` block parser → `schemas.Report` (TR8/FR5). SDK-free, never raises.

The coordinator ends its briefing with a machine-readable `CLAIMS:` block — one line per
claim in the same shape the subagents already emit:

    - <claim text> [source: <source name>, date: <YYYY-MM-DD>, url: <url>]

This module parses that block into `schemas.Claim` + `schemas.SourceRef`, so FR5 ("100% of
claims carry a source") becomes a real, deterministic test on PARSED claims rather than an
inspection of the model's prose. It is the exact sibling of `coverage_eval.parse_coverage_block`:
find the header line (case-insensitive, stripped), consume `- ...` lines until a blank or
non-matching line, tolerate malformed lines by skipping (never raise), return a plain structure.

The metadata parse is deliberately tolerant, NOT a brittle full-line regex: the claim text may
itself contain commas or colons, so we split off the LAST bracketed `[...]` group as the
metadata and treat everything before it as the claim text. Inside the brackets, fields are
`key: value` separated by commas; a missing `url` → `None` (never the literal string "None"),
a missing `date` → `""`. A line with no bracketed metadata is prose, not a claim, and is skipped.

Design mirrors `coverage_eval.py` / `triage.py`: pure, total, deterministic, imports `schemas`
only, so the unit suite runs credential-free.
"""

import schemas

#: Line that opens the coordinator's claims block (matched case-insensitively, stripped).
_CLAIMS_HEADER = "claims:"


def _parse_metadata(meta: str) -> dict[str, str]:
    """Parse the inside of a `[source: X, date: Y, url: Z]` group into a `{key: value}` dict.

    Splits on commas, then each field on its FIRST colon (so a `url:` value containing `://`
    survives). Keys are lowercased and stripped; unknown keys are kept but ignored downstream.
    Total & never raises.
    """
    fields: dict[str, str] = {}
    for part in meta.split(","):
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        key = key.strip().lower()
        if key:
            fields[key] = value.strip()
    return fields


def _parse_claim_line(body: str) -> schemas.Claim | None:
    """Parse one `- ` claim line body into a `Claim`, or None if it carries no source.

    `body` is the line with its leading `-` already stripped. Finds the LAST `[...]` group as
    the metadata (so commas/colons in the claim text are safe), requires a `source`, and builds
    `Claim(text, SourceRef(name, url, excerpt=text, date))`. `url` absent → None; `date`
    absent → "". Never raises.
    """
    open_idx = body.rfind("[")
    close_idx = body.rfind("]")
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return None  # no bracketed metadata → prose, not a claim
    text = body[:open_idx].strip()
    meta = body[open_idx + 1 : close_idx]
    fields = _parse_metadata(meta)
    source_name = fields.get("source")
    if not source_name:
        return None  # a claim without a source does not belong (FR5)
    url = fields.get("url") or None  # missing or empty → None, never the literal "None"
    if url is not None and url.lower() == "none":
        url = None
    date = fields.get("date", "")
    source = schemas.SourceRef(name=source_name, url=url, excerpt=text, date=date)
    return schemas.Claim(text=text, source=source)


def parse_claims_block(report_text: str) -> list[schemas.Claim]:
    """Parse the `CLAIMS:` block of `report_text` into `Claim`s; `[]` if none.

    Finds the first line equal to `CLAIMS:` (case-insensitive, after stripping), then consumes
    subsequent `- <claim> [source: ..., date: ..., url: ...]` lines until a blank or
    non-matching line. Malformed lines (no bracket, no source) are skipped. Total &
    deterministic, never raises — the exact control flow of `coverage_eval.parse_coverage_block`.
    """
    lines = report_text.splitlines()
    claims: list[schemas.Claim] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if stripped.lower() == _CLAIMS_HEADER:
                in_block = True
            continue
        # Inside the block: only ``- ...`` lines belong to it.
        if not stripped.startswith("-"):
            break  # blank line or prose ends the block
        claim = _parse_claim_line(stripped[1:])
        if claim is not None:
            claims.append(claim)
    return claims


def build_report(report_text: str, coverage: dict, gaps: list) -> schemas.Report:
    """Assemble a `schemas.Report` from a synthesized briefing + its coverage/gaps (TR8/FR5).

    Parses the `CLAIMS:` block into `claims`, and passes `coverage`/`gaps` through unchanged
    (they come from the Phase-3 refinement loop). `sections` is a single `{"body": report_text}`
    stub — Phase 4's operative provenance surface is `claims` + `coverage` + `gaps`; full
    per-facet section splitting is not required by any acceptance criterion. Never raises.
    """
    claims = parse_claims_block(report_text)
    return schemas.Report(
        sections=[{"body": report_text}],
        claims=claims,
        coverage=coverage,
        gaps=gaps,
    )
