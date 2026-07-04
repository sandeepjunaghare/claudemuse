"""The `web_search` subagent: retrieves sources for ONE assigned facet (TR4) and
returns a distilled summary (TR6).

Context isolation (TR6): this subagent explores in its own context window and hands
back only a condensed ~1–2k-token summary plus a structured claim→source→date list —
never its raw search transcript. Explicit context (TR2): it inherits NOTHING; the
coordinator passes the subtopic, the facet, and any query hints in the delegation
prompt. The prompt below states the *output contract*; the per-run assignment arrives
in the delegation message.
"""

from claude_agent_sdk import AgentDefinition

import config

_WEB_SEARCH_TOOL = f"mcp__{config.MCP_SERVER_NAME}__web_search"

web_search_agent = AgentDefinition(
    description=(
        "Researches ONE assigned facet of a topic: searches the corpus, then returns a "
        "distilled summary plus claim→source→date lines. Use for gathering evidence on a "
        "subtopic."
    ),
    prompt=(
        "You are a research subagent. Everything you need is in the message the "
        "coordinator sends you — you inherit no prior context, so rely only on the "
        "subtopic, facet, and query hints given there.\n\n"
        "Do this:\n"
        "1. Use the `web_search` tool to gather sources for YOUR assigned facet only. "
        "Pass the `facet` argument so you retrieve just your slice and don't overlap "
        "other subagents.\n"
        "2. Read the returned lines — each is prefixed with `[source, date]` and carries "
        "a passage and url. Those are your provenance.\n"
        "3. Return a DISTILLED result, not a transcript. Keep it under ~1–2k tokens:\n"
        "   - A short prose summary of what the sources say about your facet.\n"
        "   - Then a `CLAIMS:` section with one line per claim in the form:\n"
        "     `- <claim text> [source: <source name>, date: <YYYY-MM-DD>, url: <url>]`\n"
        "Every claim MUST carry its source and date exactly as the tool reported them. "
        "Do not invent sources or figures. If the search returns an empty result, say so "
        "plainly and report the gap rather than fabricating anything."
    ),
    model=config.WORKER_MODEL,
    tools=[_WEB_SEARCH_TOOL],
    mcpServers=[config.MCP_SERVER_NAME],
    # background=True → this subagent runs as a background task (Phase-2 spike, Path B):
    # the coordinator fires delegations back-to-back and their tasks OVERLAP in wall-clock
    # (spike measured 5 concurrent), which is the real TR2/FR3 parallelism. With
    # background=False the coordinator blocks on each result inline → sequential.
    background=True,
)
