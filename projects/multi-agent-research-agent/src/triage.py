"""Deterministic query triage: route a question to the cheap or the full path (TR3/TR10).

Multi-agent fan-out costs ~15× a single agent (TR10), so a narrow fact lookup must NOT
pay for it. `classify()` is a pure, total, deterministic function (same input → same
route, never raises, no API call) that inspects the question and returns one of two
routes:

  - `ROUTE_SINGLE_AGENT` — a short, single-fact lookup ("What year was Stable Diffusion
    released?"): answered directly by one Sonnet agent, no delegation (TR3 fallback).
  - `ROUTE_FAN_OUT` — a broad question spanning multiple facets: the full parallel
    multi-agent pipeline.

Heuristic, in order (breadth ALWAYS wins over a lookup interrogative, because the
canonical failure is under-covering breadth):
  1. Any breadth marker present            → FAN_OUT.
  2. Longer than SIMPLE_QUERY_MAX_WORDS     → FAN_OUT.
  3. Multiple coordinated clauses (list)    → FAN_OUT.
  4. Short AND a single-fact interrogative  → SINGLE_AGENT.
  5. Default                                → FAN_OUT (safe over-coverage: a false FAN_OUT
     costs tokens but never misleads; a false SINGLE_AGENT would silently miss breadth).

Deterministic by design — this is TR3's dynamic selection done in CODE, not by a model,
so it is 100% unit-testable without credentials (matching the "ground truth is structure"
ethos). The Haiku tier (`config.CLASSIFIER_MODEL`) is defined as the seam for a future
LLM classifier; that swap is DEFERRED, not built here.

SDK-free (mirrors `mocks/corpus.py`) so the unit suite imports it without the Agent SDK.
"""

import config

#: The two routes. String constants (mirrors the status-string style in `schemas.py`).
ROUTE_SINGLE_AGENT = "single_agent"  # narrow lookup → cheap single-agent fallback (no fan-out)
ROUTE_FAN_OUT = "fan_out"            # broad question → parallel multi-agent pipeline

#: Breadth markers — any of these anywhere in the question forces FAN_OUT. These signal a
#: question that spans facets, trends, or comparisons rather than a single fact.
BREADTH_MARKERS: tuple[str, ...] = (
    "impact",
    "effect",
    "landscape",
    "overview",
    "state of",
    "trends",
    "trend",
    "compare",
    "comparison",
    " vs ",
    " versus ",
    "across",
    "implications",
    "pros and cons",
    "how has",
    "how have",
    "how does",
    "how do",
    "in what ways",
)

#: Single-fact interrogatives — a SHORT question opening with one of these (and carrying no
#: breadth marker) is a narrow lookup. Trailing spaces keep prefix matches tight (e.g.
#: `"who "` matches "who created…" but not "whole"/"whose"); `"release date"` is a noun
#: phrase matched anywhere.
LOOKUP_PATTERNS: tuple[str, ...] = (
    "what year ",
    "when did ",
    "when was ",
    "who ",
    "how many ",
    "how much ",
    "release date",
    "define ",
    "what is the ",
    "what is a ",
    "what is generative",
)


def _has_breadth_marker(q: str) -> bool:
    """True if any breadth marker appears in the normalized question."""
    return any(marker in q for marker in BREADTH_MARKERS)


def _is_lookup(q: str) -> bool:
    """True if a single-fact interrogative appears in the question.

    Only consulted for SHORT, non-breadth, non-list questions (steps 1–3 already returned
    FAN_OUT otherwise), so a plain substring test is tight enough — the trailing-space
    patterns (`"who "`) avoid matching "whose"/"whole".
    """
    return any(p in q for p in LOOKUP_PATTERNS)


def _has_multiple_clauses(q: str) -> bool:
    """True for a comma-separated list of ≥2 items — a breadth signal ('art, music, and film').

    A single comma plus a coordinating ' and ' (the Oxford-list shape) or two-or-more
    commas both indicate several facets bundled into one question.
    """
    commas = q.count(",")
    return commas >= 2 or (commas >= 1 and " and " in q)


def classify(question: str) -> str:
    """Route `question` to `ROUTE_SINGLE_AGENT` or `ROUTE_FAN_OUT` (TR3). Never raises.

    Pure and deterministic: normalizes to lowercase, then applies the ordered heuristic
    documented at module top. Breadth beats a lookup interrogative; the default is
    FAN_OUT (safe over-coverage).
    """
    q = question.strip().lower()
    word_count = len(q.split())

    # 1–3: any breadth signal → the full pipeline.
    if _has_breadth_marker(q):
        return ROUTE_FAN_OUT
    if word_count > config.SIMPLE_QUERY_MAX_WORDS:
        return ROUTE_FAN_OUT
    if _has_multiple_clauses(q):
        return ROUTE_FAN_OUT

    # 4: short, single-fact lookup with no breadth signal → cheap single-agent path.
    if word_count <= config.SIMPLE_QUERY_MAX_WORDS and _is_lookup(q):
        return ROUTE_SINGLE_AGENT

    # 5: ambiguous → default to fan-out (missing breadth is the costly failure, not tokens).
    return ROUTE_FAN_OUT
