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


# --- TR7: timeout / access-failure envelope -----------------------------------

def test_timeout_source_yields_partial_with_error_block():
    """A music sweep still yields D003 AND flags the RAC timeout — music is NOT lost."""
    text = format_search("AI", facet="music")
    # The available evidence (D003) survives.
    assert "Music Industry Digest" in text or "10 million" in text
    # The unavailable source is flagged with a retryable ERROR block.
    assert "ERROR:" in text
    assert "Recording Artists Coalition" in text
    assert "access_timeout" in text and "retryable: true" in text


def test_by_reference_timeout_is_full_access_failure():
    """Fetching the timed-out source by name → ERROR-only, no fabricated content."""
    text = format_search("Recording Artists Coalition")
    assert "ERROR:" in text and "access_timeout" in text
    # No fabricated RAC content — the excerpt is never rendered.
    assert "consent-based AI training" not in text
    assert "voice cloning" not in text


def test_access_failure_distinct_from_valid_empty():
    """A retryable access failure is distinguishable from a (non-retryable) valid empty."""
    access = format_search("Recording Artists Coalition")
    empty = format_search("zzzznotarealterm")
    # Access failure carries the ERROR/retryable markers…
    assert "ERROR:" in access and "retryable: true" in access
    # …the valid empty does not.
    assert "ERROR:" not in empty and "retryable" not in empty
    assert "No sources found" in empty


def test_clean_facet_has_no_error_block():
    """A fully-available facet (film) renders cleanly with no ERROR block."""
    text = format_search("AI film studios", facet="film")
    assert "ERROR:" not in text
    assert "retryable" not in text
