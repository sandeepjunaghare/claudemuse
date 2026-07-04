"""Deterministic unit table for `coverage_eval` (TR4). No SDK, no API.

The evaluator is a pure function, so this is the ground-truth check that coverage
verification is correct: a clean COVERAGE block parses to canonical facets, free-text
labels map via aliases, gaps are computed against the expected set, and the prose-scan
fallback protects a block-less report from false refinement. Same input → same output.
"""

import pytest

import coverage_eval as ce
from mocks import corpus

FACETS = corpus.FACETS  # ["visual_art", "music", "writing", "film"]

_FULL_BLOCK = """\
Some briefing prose here.

COVERAGE:
- visual art: covered
- music: covered
- writing: covered
- film: covered
"""

_PARTIAL_BLOCK = """\
COVERAGE:
- visual art: covered
- music: covered
"""

_FREE_TEXT_BLOCK = """\
COVERAGE:
- visual arts: covered
- music: covered
- written word: covered
- movies: covered
"""


# --- parse_coverage_block -----------------------------------------------------

def test_parse_full_block_maps_all_canonical_facets():
    parsed = ce.parse_coverage_block(_FULL_BLOCK)
    assert parsed == {f: ce.STATUS_COVERED for f in FACETS}


def test_parse_free_text_labels_map_via_aliases():
    parsed = ce.parse_coverage_block(_FREE_TEXT_BLOCK)
    # "visual arts", "written word", "movies" all resolve to canonical facets.
    assert set(parsed) == set(FACETS)
    assert all(status == ce.STATUS_COVERED for status in parsed.values())


def test_parse_no_block_returns_empty():
    assert ce.parse_coverage_block("A report with no coverage section at all.") == {}


def test_parse_block_stops_at_blank_line():
    text = "COVERAGE:\n- music: covered\n\n- film: covered"  # film is after the block ends
    parsed = ce.parse_coverage_block(text)
    assert parsed == {"music": ce.STATUS_COVERED}


def test_parse_unknown_status_normalizes_to_partial():
    parsed = ce.parse_coverage_block("COVERAGE:\n- music: sort-of")
    assert parsed == {"music": ce.STATUS_PARTIAL}


# --- evaluate -----------------------------------------------------------------

def test_evaluate_full_coverage_no_gaps():
    result = ce.evaluate(_FULL_BLOCK, FACETS)
    assert result.gaps == []
    assert result.covered == set(FACETS)
    assert result.map == {f: ce.STATUS_COVERED for f in FACETS}


def test_evaluate_partial_block_reports_missing_in_expected_order():
    result = ce.evaluate(_PARTIAL_BLOCK, FACETS)
    # gaps follow `expected` order, not declaration order.
    assert result.gaps == ["writing", "film"]
    assert result.covered == {"visual_art", "music"}


def test_evaluate_gap_and_partial_statuses_count_as_uncovered():
    block = "COVERAGE:\n- visual art: covered\n- music: partial\n- writing: gap\n- film: covered"
    result = ce.evaluate(block, FACETS)
    # Only `covered` counts; `partial`/`gap` are treated as not-yet-covered.
    assert result.gaps == ["music", "writing"]


def test_evaluate_fallback_prose_mentions_all_four_no_false_refinement():
    # No COVERAGE block, but prose mentions every facet → no gaps (avoid needless refinement).
    prose = "This covers visual art and illustration, music and songs, writing by authors, and film."
    result = ce.evaluate(prose, FACETS)
    assert result.gaps == []
    assert result.covered == set(FACETS)


def test_evaluate_fallback_prose_mentions_only_two():
    prose = "This briefing discusses visual art and music at length, with sources."
    result = ce.evaluate(prose, FACETS)
    assert result.gaps == ["writing", "film"]


def test_music_video_prose_not_miscounted_as_film():
    # Alias-collision guard: "music video" mentions music, not film (no bare 'video' alias).
    prose = "The report examines the AI music video trend and its songs."
    result = ce.evaluate(prose, FACETS)
    assert "music" in result.covered
    assert "film" in result.gaps


# --- canonical_facet ----------------------------------------------------------

@pytest.mark.parametrize(
    "label,expected",
    [
        ("visual arts", "visual_art"),
        ("Visual Art", "visual_art"),
        ("music", "music"),
        ("music video", "music"),  # music wins over film
        ("written word", "writing"),
        ("authors and publishing", "writing"),
        ("movies", "film"),
        ("cinema", "film"),
        ("quantum physics", None),
    ],
)
def test_canonical_facet_mapping(label, expected):
    assert ce.canonical_facet(label) == expected
