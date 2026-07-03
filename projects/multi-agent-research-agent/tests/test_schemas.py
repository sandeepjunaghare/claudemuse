"""Unit: schema round-trip + the content/metadata separation that keeps provenance."""

import schemas


def _source(name="ArtMarket Report", date="2024-11-01"):
    return schemas.SourceRef(name=name, url="https://example.com/x", excerpt="…", date=date)


def test_claim_carries_source():
    c = schemas.Claim(text="AI-art market ~$3.2B in 2024", source=_source())
    assert c.source.name == "ArtMarket Report"
    assert c.source.date == "2024-11-01"  # date preserved as plain ISO string


def test_subagent_result_separates_content_from_metadata():
    r = schemas.SubagentResult(
        facet="visual_art",
        summary="AI is reshaping visual art.",
        claims=[schemas.Claim("x", _source())],
    )
    assert r.status == "ok"  # default; Phase 4 uses this for partial/failed
    assert r.claims[0].source.date  # metadata rides alongside content, not merged in


def test_report_defaults_are_staged_empty():
    """coverage/gaps default empty — staged for Phase 3/4, not required in Phase 1."""
    r = schemas.Report(sections=[], claims=[])
    assert r.coverage == {}
    assert r.gaps == []


def test_all_claims_have_source_invariant():
    good = schemas.Report(sections=[], claims=[schemas.Claim("x", _source())])
    assert good.all_claims_have_source() is True

    # An orphan fact (source not a SourceRef) fails the 100%-citation invariant (FR5).
    orphan = schemas.Report(sections=[], claims=[schemas.Claim("y", None)])  # type: ignore[arg-type]
    assert orphan.all_claims_have_source() is False

    assert schemas.Report(sections=[], claims=[]).all_claims_have_source() is True
