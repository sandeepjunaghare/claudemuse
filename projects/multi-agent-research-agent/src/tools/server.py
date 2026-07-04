"""The `web_search` tool, served as an EXTERNAL stdio MCP server (FastMCP).

Why external, not in-process (`create_sdk_mcp_server`): Phase-1 diagnostics found that
an in-process SDK MCP tool is bridged to the CLI over the SDK↔CLI *control channel*,
and when a **subagent** (freshly spawned by the CLI) calls that tool, the round-trip
races at subagent startup and intermittently returns a transport-level "Stream closed"
error — sometimes every call in a run fails. In a multi-agent system the subagents MUST
call tools reliably, so we serve the tool as a standalone stdio process the CLI launches
and talks to directly. Both the coordinator and its subagents reach it reliably.

(This is a deliberate divergence from the sibling `customer-support`, whose in-process
server works only because that agent has no subagents. See memory mar-agent-sdk-delegation.)

Provenance contract (unchanged): each hit's source, date, excerpt, and url are encoded
in the returned TEXT — `structuredContent` is dropped before the model sees it, so the
text is the operative surface. `format_search` is a pure function so it is unit-testable
without spawning the server or the SDK.

Run standalone (what the CLI does):  python src/tools/server.py
"""

import sys
from pathlib import Path

# Make this file runnable as a standalone subprocess: put `src/` on the path so the
# CLI-launched process can import `config` and `mocks.corpus` with flat imports.
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from claude_agent_sdk import create_sdk_mcp_server, tool as sdk_tool
from mcp.server.fastmcp import FastMCP

import config
import errors
from mocks import corpus

#: Shared tool description (purpose, inputs, returns) — used by BOTH server flavors below.
_WEB_SEARCH_DESCRIPTION = (
    "Search the research corpus for sources on a topic and return matching passages "
    "WITH their provenance (source name, publication date, excerpt, url). Use this to "
    "gather evidence for a research subtopic before summarizing it.\n\n"
    "Inputs: `query` (required) — keywords describing what to find, e.g. "
    "\"AI impact on film production\" or \"copyright AI-generated art\"; `facet` "
    "(optional) — restrict results to one facet of the topic, one of: visual_art, "
    "music, writing, film. Pass `facet` when you have been assigned a specific facet "
    "so you retrieve only your slice and avoid overlapping other subagents.\n\n"
    "Returns: one line per matching source, each prefixed with `[source, date]` and "
    "including a passage and url. If nothing matches you get an explicit empty result "
    "(a valid 'no sources found', not an error) — do not invent sources to fill a gap. "
    "You can also pass an exact source name or document id as the `query` to fetch a "
    "specific document by reference.\n\n"
    "A source may be temporarily UNAVAILABLE (its endpoint timed out). When that happens "
    "the result includes a machine-readable `ERROR:` block naming the unavailable source, "
    "marked `retryable: true`. This is an ACCESS FAILURE — DISTINCT from a valid empty "
    "result — and it may be retried. Any passages shown ABOVE the `ERROR:` block are still "
    "valid, usable results: use them, and pass the unavailable-source note along so it can "
    "be annotated as a gap."
)


def _format_hit(doc: dict) -> str:
    """One provenance-bearing line per hit: `[source, date]` + facet + excerpt + url."""
    excerpt = doc["content"].strip()
    return f"[{doc['source']}, {doc['date']}] (facet: {doc['facet']}) {excerpt} (url: {doc['url']})"


def format_search(query: str, facet: str | None = None) -> str:
    """Search the corpus and render results as provenance-bearing text (pure, testable).

    Four outcomes (TR7), all encoded in TEXT (the surface the model sees):
      - CLEAN: one `[source, date]` line per hit.
      - VALID EMPTY: an explicit "no sources found" message — NOT an error, NOT retryable.
      - PARTIAL (some hits available, one timed out): the available lines PLUS a retryable
        `ERROR:` block naming the unavailable source — the good evidence is not discarded.
      - FULL ACCESS FAILURE (the ONLY match is a timed-out source, e.g. a by-reference fetch
        of D004): just the retryable `ERROR:` block, no fabricated content.

    Timeout is read from `doc.get("timeout")` here (the tool), so `mocks/corpus.py` stays
    data-only. Nothing actually blocks — the timeout is *simulated* via the marker. Pure &
    never raises.
    """
    hits = corpus.search(query, facet=facet)
    if not hits:
        scope = f" in facet '{facet}'" if facet else ""
        return (
            f"No sources found for query {query!r}{scope}. This is a valid empty result — "
            "report the gap; do not fabricate a source."
        )

    # By-reference resolution: if the query EXACTLY names a hit's source or id, this is a
    # fetch of that specific document — narrow to it, not to fuzzy term-neighbors. This makes
    # a by-name fetch of an unavailable source (D004) a true full access failure, and keeps
    # `mocks/corpus.py` data-only (the resolution lives here in the tool, not in the corpus).
    q = query.strip().lower()
    exact = [doc for doc in hits if q in (doc["id"].lower(), doc["source"].lower())]
    if exact:
        hits = exact

    available = [doc for doc in hits if not doc.get("timeout")]
    unavailable = [doc for doc in hits if doc.get("timeout")]

    if not unavailable:
        # CLEAN: every hit is reachable.
        lines = [_format_hit(doc) for doc in available]
        return f"Found {len(available)} source(s) for {query!r}:\n" + "\n".join(lines)

    failed_source = unavailable[0]["source"]
    if available:
        # PARTIAL: keep the reachable evidence, then append the retryable ERROR block.
        lines = [_format_hit(doc) for doc in available]
        envelope = errors.ErrorEnvelope(
            type=errors.FAILURE_ACCESS_TIMEOUT,
            attempted_query=query,
            is_retryable=True,
            failed_source=failed_source,
            alternative=(
                "use the sources above; report the unavailable source as a gap "
                "(one unavailable source does not make the facet a gap)."
            ),
        )
        return (
            f"Found {len(available)} source(s) for {query!r} "
            f"(1 source unavailable):\n"
            + "\n".join(lines)
            + "\n\n"
            + envelope.render()
        )

    # FULL ACCESS FAILURE: the only match timed out — no content, just the retryable error.
    envelope = errors.ErrorEnvelope(
        type=errors.FAILURE_ACCESS_TIMEOUT,
        attempted_query=query,
        is_retryable=True,
        failed_source=failed_source,
        alternative=(
            "this specific source is unavailable — retry, or annotate it as an "
            "unavailable source; do not fabricate its content."
        ),
    )
    return envelope.render()


mcp = FastMCP(config.MCP_SERVER_NAME)


@mcp.tool(description=_WEB_SEARCH_DESCRIPTION)
async def web_search(query: str, facet: str | None = None) -> str:
    """Search the seeded corpus; return provenance-bearing lines of text (external stdio)."""
    return format_search(query, facet=facet)


# --- In-process server (single-agent fallback only) ------------------------------------
# The external stdio server above is required for the COORDINATOR path: an in-process tool
# races with "Stream closed" when a freshly-spawned SUBAGENT calls it (Phase-1 finding).
# But the single-agent fallback (build_single_agent_options) has NO subagents, and a
# top-level `tools=[]` agent does NOT get the external-stdio tool surfaced to it (the
# Phase-2 diagnostic showed it reports "no web_search tool"). The sibling `customer-support`
# proves the fix: an IN-PROCESS `create_sdk_mcp_server` IS surfaced to a `tools=[]` agent.
# So the single agent uses this in-process server; both flavors share `format_search`.

_WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Keywords, or an exact source name / document id."},
        "facet": {
            "type": "string",
            "description": "Optional facet filter: visual_art, music, writing, or film.",
        },
    },
    "required": ["query"],
}


@sdk_tool("web_search", _WEB_SEARCH_DESCRIPTION, _WEB_SEARCH_SCHEMA)
async def _web_search_in_process(args: dict) -> dict:
    """In-process `web_search` for the single-agent fallback; same corpus, same provenance."""
    text = format_search(args["query"], facet=args.get("facet"))
    return {"content": [{"type": "text", "text": text}]}


#: In-process MCP server object — passed as `mcp_servers={NAME: research_server}` by the
#: single-agent fallback (NOT the coordinator, which uses the external stdio config).
research_server = create_sdk_mcp_server(
    name=config.MCP_SERVER_NAME,
    version="1.0.0",
    tools=[_web_search_in_process],
)


if __name__ == "__main__":
    # Default transport is stdio — this is how the CLI launches the EXTERNAL server for the
    # coordinator and its subagents.
    mcp.run()
