"""Unit: the web_search tool's search/render logic + the 'provenance-in-text' contract.

The tool is served as an external stdio MCP process, but its core is the pure
`format_search(query, facet)` function — deterministic and free to test. The key
assertion is that source + date land in the returned TEXT, because `structuredContent`
is dropped before the model sees it, so text is the only provenance surface.
"""

from tools.server import format_search


def test_hit_encodes_source_and_date_in_text():
    text = format_search("AI film studios", facet="film")
    assert "Film Tech Quarterly" in text or "Screen Production Institute" in text
    assert "2023-05-01" in text or "2025-03-01" in text
    assert "[" in text and "]" in text  # the [source, date] citation shape
    assert "url:" in text  # provenance includes the url


def test_facet_filter_scopes_results():
    text = format_search("AI", facet="music")
    assert "facet: music" in text
    assert "facet: film" not in text  # scoped to music only


def test_empty_result_is_valid_not_error():
    """No match yields an explicit empty-result message (not an error, not a fabrication)."""
    text = format_search("zzzznotarealterm")
    assert "No sources found" in text


def test_fetch_by_reference_returns_the_document():
    """Passing an exact source name fetches that document (doc_analysis path)."""
    text = format_search("Film Tech Quarterly")
    assert "Film Tech Quarterly" in text
    assert "40%" in text  # the figure from D007
