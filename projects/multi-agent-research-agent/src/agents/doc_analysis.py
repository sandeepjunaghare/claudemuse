"""The `doc_analysis` subagent: extracts claims from a SPECIFIC document (TR2/TR6).

Where `web_search` casts a facet-wide net, this subagent is pointed at one document
by reference (id or source name) with an extraction goal, and returns the structured
claims/figures it finds. Phase-1 simplification: it fetches by reference through the
same `web_search` tool (querying the document's id/source) rather than a dedicated
fetch tool — flagged for a Phase 4 revisit when provenance may need a distinct path.

Explicit context (TR2): the target document reference and the extraction goal arrive
in the coordinator's delegation message; this subagent inherits nothing.
"""

from claude_agent_sdk import AgentDefinition

import config

_WEB_SEARCH_TOOL = f"mcp__{config.MCP_SERVER_NAME}__web_search"

doc_analysis_agent = AgentDefinition(
    description=(
        "Extracts claims and figures from ONE specific document identified by reference "
        "(document id or source name), given an extraction goal. Use for close reading of "
        "a named source rather than broad facet search."
    ),
    prompt=(
        "You are a document-analysis subagent. Everything you need is in the coordinator's "
        "message — the document reference (its id or source name) and what to extract. You "
        "inherit no prior context.\n\n"
        "Do this:\n"
        "1. Use the `web_search` tool to fetch the referenced document by passing its id or "
        "source name as the `query` (e.g. query='D007' or query='Film Tech Quarterly').\n"
        "2. If the fetch returns an `ERROR:` block marked `retryable: true` (e.g. an "
        "`access_timeout` — the source's endpoint is unavailable), retry the SAME fetch up "
        "to 2 times (keep in sync with config.MAX_TOOL_RETRIES). If it STILL fails, do NOT "
        "fabricate the document's content — instead return a structured failure stating (a) "
        "the failure type, (b) the query you attempted, (c) any partial results you did "
        "obtain, and (d) an alternative (e.g. 'this specific source is unavailable — "
        "recommend annotating it as a gap'). This access failure is DISTINCT from a valid "
        "empty result (which means the corpus genuinely has no such source — report that as "
        "an empty finding, not a failure).\n"
        "3. From the returned passage, extract the specific claims/figures the coordinator "
        "asked for. Each returned line is prefixed with `[source, date]` — that is the "
        "provenance you must preserve.\n"
        "4. Return a DISTILLED result (under ~1–2k tokens), not a transcript:\n"
        "   - A one- or two-sentence summary of the document as it bears on the goal.\n"
        "   - Then a `CLAIMS:` section, one line per extracted claim in the form:\n"
        "     `- <claim text> [source: <source name>, date: <YYYY-MM-DD>, url: <url>]`\n"
        "Preserve the source and date verbatim; never invent a figure. If the document "
        "cannot be found, report that plainly rather than guessing."
    ),
    model=config.WORKER_MODEL,
    tools=[_WEB_SEARCH_TOOL],
    mcpServers=[config.MCP_SERVER_NAME],
    # background=True so this subagent overlaps the others when the coordinator fans out
    # (Phase-2 spike, Path B — see web_search.py for the full rationale).
    background=True,
)
