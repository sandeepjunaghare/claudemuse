"""Deterministic unit table for `provenance` (TR8/FR5). No SDK, no API.

Ground truth that the `CLAIMS:` block parses into `Claim`+`SourceRef` correctly and that FR5
("100% of claims carry a source") holds on the PARSED claims — not on the model's prose. The
parse must be tolerant (commas/colons in claim text, missing url) and never raise.
"""

import provenance
import schemas

_WELL_FORMED = """\
Some briefing prose.

CLAIMS:
- AI art market ~$3.2B in 2024 [source: ArtMarket Report, date: 2024-11-01, url: https://example.com/artmarket]
- 40% of film studios used AI tools [source: Film Tech Quarterly, date: 2023-05-01, url: https://example.com/filmtech]
- 55% of film studios used AI tools [source: Screen Production Institute, date: 2025-03-01, url: https://example.com/spi]
"""


def test_parse_well_formed_block_builds_claims_with_sources():
    claims = provenance.parse_claims_block(_WELL_FORMED)
    assert len(claims) == 3
    for c in claims:
        assert isinstance(c.source, schemas.SourceRef)
    first = claims[0]
    assert first.source.name == "ArtMarket Report"
    assert first.source.date == "2024-11-01"
    assert first.source.url == "https://example.com/artmarket"
    assert first.source.excerpt == first.text  # excerpt = the claim text


def test_missing_url_yields_none_not_string():
    block = "CLAIMS:\n- A claim [source: Some Source, date: 2024-01-01]"
    claims = provenance.parse_claims_block(block)
    assert len(claims) == 1
    assert claims[0].source.url is None  # not the literal "None"


def test_literal_none_url_yields_none():
    block = "CLAIMS:\n- A claim [source: Some Source, date: 2024-01-01, url: None]"
    claims = provenance.parse_claims_block(block)
    assert claims[0].source.url is None


def test_comma_in_claim_text_is_tolerated():
    block = "CLAIMS:\n- Revenue rose, then fell [source: Report X, date: 2024-01-01, url: https://x]"
    claims = provenance.parse_claims_block(block)
    assert len(claims) == 1
    assert claims[0].text == "Revenue rose, then fell"
    assert claims[0].source.name == "Report X"


def test_colon_in_claim_text_is_tolerated():
    block = "CLAIMS:\n- Finding: AI adoption grew [source: Report Y, date: 2025-01-01, url: https://y]"
    claims = provenance.parse_claims_block(block)
    assert len(claims) == 1
    assert claims[0].text == "Finding: AI adoption grew"
    assert claims[0].source.name == "Report Y"


def test_no_claims_block_returns_empty():
    assert provenance.parse_claims_block("A report with no claims section at all.") == []


def test_malformed_line_is_skipped_others_kept():
    block = (
        "CLAIMS:\n"
        "- Good claim [source: Source A, date: 2024-01-01, url: https://a]\n"
        "- A prose line with no bracket metadata\n"
        "- Another good claim [source: Source B, date: 2024-02-01, url: https://b]"
    )
    claims = provenance.parse_claims_block(block)
    assert len(claims) == 2
    assert {c.source.name for c in claims} == {"Source A", "Source B"}


def test_line_without_source_is_skipped():
    block = "CLAIMS:\n- A claim [date: 2024-01-01, url: https://a]"
    assert provenance.parse_claims_block(block) == []


def test_block_stops_at_blank_line():
    block = "CLAIMS:\n- One [source: A, date: 2024-01-01]\n\n- Two [source: B, date: 2024-02-01]"
    claims = provenance.parse_claims_block(block)
    assert len(claims) == 1
    assert claims[0].source.name == "A"


# --- build_report -------------------------------------------------------------

def test_build_report_satisfies_fr5_and_passes_coverage_through():
    coverage = {"visual_art": "covered", "film": "covered"}
    gaps: list = []
    report = provenance.build_report(_WELL_FORMED, coverage, gaps)
    assert report.all_claims_have_source() is True  # FR5 on parsed claims
    assert len(report.claims) == 3
    assert report.coverage == coverage  # passed through unchanged
    assert report.gaps == gaps


def test_build_report_empty_claims_is_vacuously_cited():
    report = provenance.build_report("No claims block here.", {}, [])
    assert report.claims == []
    assert report.all_claims_have_source() is True  # vacuously True
