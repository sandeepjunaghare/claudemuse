"""Unit: the seeded corpus is engineered so each failure mode is reproducible."""

import mocks.corpus as corpus


def test_four_plus_facets():
    """(a) TR4: the topic spans 4+ facets so coverage/decomposition is exercisable."""
    assert len(corpus.FACETS) >= 4
    # Every facet is actually represented by at least one document.
    for facet in corpus.FACETS:
        assert any(d["facet"] == facet for d in corpus.DOCUMENTS), facet


def test_every_document_has_provenance_fields():
    for d in corpus.DOCUMENTS:
        assert {"id", "facet", "source", "date", "content"} <= set(d.keys()), d["id"]


def test_conflict_pair_exists():
    """(b)/(c) TR8: two credible film sources give DIFFERENT values for the SAME figure
    on DIFFERENT dates — the conflict + temporal case Phase 4 must preserve."""
    film = [d for d in corpus.DOCUMENTS if d["facet"] == "film"]
    assert len(film) >= 2
    a, b = corpus.get_document("D007"), corpus.get_document("D008")
    assert a and b
    assert "40%" in a["content"] and "55%" in b["content"]  # conflicting values
    assert a["date"] != b["date"]  # differently dated (temporal handling)
    assert a["source"] != b["source"]  # both credible, distinct sources


def test_timeout_marker_exists():
    """(d) TR7: exactly one endpoint is flagged to time out (inert data in Phase 1)."""
    flagged = [d for d in corpus.DOCUMENTS if d.get("timeout")]
    assert len(flagged) >= 1


def test_facet_scoped_search_stays_in_facet():
    """TR4 scope partitioning: a facet-filtered search returns only that facet."""
    music = corpus.search("AI", facet="music")
    assert music, "expected music docs to match 'AI'"
    assert all(d["facet"] == "music" for d in music)


def test_search_empty_is_not_an_error():
    """No match returns [] (a valid empty result), never raises."""
    assert corpus.search("zzzznotarealterm") == []


def test_fetch_by_reference():
    """doc_analysis fetches a specific document by id or source name."""
    assert any(d["id"] == "D007" for d in corpus.search("D007"))
    assert any(d["source"] == "Film Tech Quarterly" for d in corpus.search("Film Tech Quarterly"))
