"""Seeded research corpus for "impact of AI on creative industries" + a `search` seam.

Intentionally SDK-free (mirrors the sibling `mocks/fixtures.py`) so it unit-tests in
isolation without credentials. The seed data is *engineered* so each requirement's
failure mode is deterministic and reproducible:

  (a) 4+ facets — visual_art, music, writing, film — so decomposition/coverage (TR4)
      is exercisable and the "only one facet" trap (FR2) is detectable in tests.
  (b) a CONFLICT PAIR — two credible sources giving different values for the SAME
      figure (film-industry AI-tool adoption: 40% vs 55%) so conflict handling (TR8)
      can be exercised in Phase 4.
  (c) DIFFERENTLY-DATED sources — the conflict pair is 2023 vs 2025, so a temporal
      difference is not misread as a contradiction (TR8).
  (d) a TIMEOUT MARKER — one doc flagged `{"timeout": True}` so a simulated endpoint
      failure (TR7) can be triggered in Phase 4.

Phase-1 scope: (b)/(c)/(d) are inert *data* here — `search` returns clean results and
ignores the timeout marker. The behaviors that exercise them (conflict annotation,
retry + partial-result propagation) arrive in Phases 3–4 without reshaping this module.
"""

#: The facets the topic decomposes into — exported so coverage tests (TR4) can assert
#: the report spans the whole topic, not just one facet.
FACETS: list[str] = ["visual_art", "music", "writing", "film"]

#: Each document: {id, facet, source, date, url, content}. Optional `timeout: True`
#: marks the endpoint that will fail in Phase 4 (inert now).
DOCUMENTS: list[dict] = [
    # --- visual_art ---------------------------------------------------------
    {
        "id": "D001",
        "facet": "visual_art",
        "source": "ArtMarket Report",
        "date": "2024-11-01",
        "url": "https://example.com/artmarket-2024",
        "content": (
            "The global market for AI-generated visual art reached an estimated $3.2 "
            "billion in 2024, driven by text-to-image tools like Stable Diffusion and "
            "Midjourney. Traditional illustrators report both new revenue streams and "
            "displacement pressure."
        ),
    },
    {
        "id": "D002",
        "facet": "visual_art",
        "source": "Copyright Law Review",
        "date": "2024-06-15",
        "url": "https://example.com/copyright-ai-art",
        "content": (
            "Courts in 2024 held that purely AI-generated images without meaningful human "
            "authorship are not eligible for copyright, reshaping how visual artists "
            "incorporate AI into their workflows."
        ),
    },
    # --- music --------------------------------------------------------------
    {
        "id": "D003",
        "facet": "music",
        "source": "Music Industry Digest",
        "date": "2025-02-20",
        "url": "https://example.com/ai-music-2025",
        "content": (
            "AI music generation platforms produced over 10 million tracks in 2024. "
            "Streaming services began flagging AI-generated songs, and songwriters "
            "negotiated new royalty terms to account for AI training on their catalogs."
        ),
    },
    {
        "id": "D004",
        "facet": "music",
        "source": "Recording Artists Coalition",
        "date": "2024-09-10",
        "url": "https://example.com/rac-ai-statement",
        # This is the endpoint engineered to TIME OUT in Phase 4 (TR7). Inert in Phase 1.
        "timeout": True,
        "content": (
            "A coalition of recording artists called for consent-based AI training and "
            "clear labeling of AI-assisted music, warning that unlicensed voice cloning "
            "threatens performers' livelihoods."
        ),
    },
    # --- writing ------------------------------------------------------------
    {
        "id": "D005",
        "facet": "writing",
        "source": "Publishing Weekly",
        "date": "2025-01-12",
        "url": "https://example.com/ai-publishing-2025",
        "content": (
            "Publishers reported a surge in AI-assisted manuscripts in 2024. Several "
            "houses adopted disclosure policies requiring authors to declare AI use, "
            "while freelance writers cited downward pressure on rates for routine "
            "content."
        ),
    },
    {
        "id": "D006",
        "facet": "writing",
        "source": "Authors Guild Survey",
        "date": "2024-08-05",
        "url": "https://example.com/authors-guild-survey",
        "content": (
            "In an Authors Guild survey, a majority of professional writers expressed "
            "concern that AI tools trained on their work without permission could reduce "
            "their income, even as some adopted AI for drafting and editing."
        ),
    },
    # --- film ---------------------------------------------------------------
    # (b)/(c) CONFLICT PAIR: same figure (share of film studios using AI tools),
    # different values (40% vs 55%), different dates (2023 vs 2025), both credible.
    {
        "id": "D007",
        "facet": "film",
        "source": "Film Tech Quarterly",
        "date": "2023-05-01",
        "url": "https://example.com/filmtech-2023",
        "content": (
            "As of 2023, roughly 40% of film studios reported using AI tools for "
            "pre-visualization, editing, or visual effects, according to Film Tech "
            "Quarterly's annual survey."
        ),
    },
    {
        "id": "D008",
        "facet": "film",
        "source": "Screen Production Institute",
        "date": "2025-03-01",
        "url": "https://example.com/spi-2025",
        "content": (
            "By 2025, the Screen Production Institute found that 55% of film studios had "
            "adopted AI tools across production, up sharply from prior years, with the "
            "largest gains in visual effects and dubbing."
        ),
    },
]


def get_document(doc_id: str) -> dict | None:
    """Return the document with `doc_id`, or None if unknown. Never raises."""
    for doc in DOCUMENTS:
        if doc["id"] == doc_id:
            return doc
    return None


def search(query: str, facet: str | None = None) -> list[dict]:
    """Case-insensitive keyword search over the corpus, optionally scoped to a facet.

    Matches when any whitespace-delimited term of `query` is a substring of the
    document's `content` or `facet`. Also matches a document by its exact `id` or
    `source` so `doc_analysis` can fetch a specific document by reference. When
    `facet` is given, only documents in that facet are considered (so a subagent
    assigned one facet does not retrieve another's — TR4 scope partitioning).
    Never raises; returns [] on no match (a *valid empty* result, distinct from an
    access failure — that distinction is wired in Phase 4).
    """
    terms = [t for t in query.lower().split() if t]
    results: list[dict] = []
    for doc in DOCUMENTS:
        if facet is not None and doc["facet"] != facet:
            continue
        haystack = f"{doc['content']} {doc['facet']}".lower()
        by_id = query.strip().lower() in (doc["id"].lower(), doc["source"].lower())
        by_term = any(term in haystack for term in terms)
        if by_id or by_term:
            results.append(doc)
    return results
