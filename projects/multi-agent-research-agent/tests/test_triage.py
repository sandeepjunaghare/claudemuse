"""Deterministic unit table for `triage.classify` (TR3). No SDK, no API.

The classifier is a pure function, so this is the ground-truth check that dynamic
selection routes correctly: canonical broad questions → fan-out, canonical narrow
lookups → single-agent, ambiguous → the safe fan-out default. Same input → same route.
"""

import pytest

import triage

# --- Narrow lookups → SINGLE_AGENT (short, single-fact interrogative, no breadth) -------
SINGLE_AGENT_CASES = [
    "What year was Stable Diffusion released?",
    "When did Midjourney launch?",
    "When was DALL·E first released?",
    "Who created DALL·E?",
    "How many AI music tracks were produced in 2024?",
    "How much did the AI art market grow?",
    "Define generative AI.",
    "What is the release date of Sora?",
    "What is generative AI?",
]

# --- Broad questions → FAN_OUT (breadth marker, multi-clause, or long) -------------------
FAN_OUT_CASES = [
    "What is the impact of AI on creative industries?",
    "Compare AI adoption in film vs music",
    "Give an overview of AI's effect on writing, art, and film",
    "State of AI in the creative economy",
    "What are the implications of AI across the creative sector?",
    "How has AI changed music production?",
    "Analyze AI adoption trends in film and television",
    # Long, multi-clause question — over SIMPLE_QUERY_MAX_WORDS words.
    "How have artists, musicians, writers, and filmmakers responded to the rapid rise of "
    "generative AI tools in their day-to-day creative and commercial work?",
]

# --- Ambiguous / medium → default FAN_OUT (documents the safe-over-coverage bias) --------
DEFAULT_FAN_OUT_CASES = [
    "Tell me something about AI and artists",
    "AI in the music business",
    "Describe how filmmakers use new tools",
]


@pytest.mark.parametrize("question", SINGLE_AGENT_CASES)
def test_narrow_lookups_route_single_agent(question):
    assert triage.classify(question) == triage.ROUTE_SINGLE_AGENT


@pytest.mark.parametrize("question", FAN_OUT_CASES)
def test_broad_questions_route_fan_out(question):
    assert triage.classify(question) == triage.ROUTE_FAN_OUT


@pytest.mark.parametrize("question", DEFAULT_FAN_OUT_CASES)
def test_ambiguous_defaults_to_fan_out(question):
    # The canonical failure is UNDER-covering breadth, so an ambiguous question must
    # fall through to fan-out, never to the single-agent path.
    assert triage.classify(question) == triage.ROUTE_FAN_OUT


def test_breadth_marker_beats_lookup_interrogative():
    # "What is the impact of…" opens like a lookup ("what is the") but carries a breadth
    # marker ("impact") — breadth MUST win.
    assert triage.classify("What is the impact of AI on visual art?") == triage.ROUTE_FAN_OUT


def test_classify_is_total_and_deterministic():
    # Never raises on odd input; same input → same output.
    for q in ("", "   ", "?", "AI"):
        first = triage.classify(q)
        assert first in (triage.ROUTE_SINGLE_AGENT, triage.ROUTE_FAN_OUT)
        assert triage.classify(q) == first


def test_routes_are_distinct_constants():
    assert triage.ROUTE_SINGLE_AGENT != triage.ROUTE_FAN_OUT
