"""The coordinator: the hub that decomposes, delegates, and synthesizes (TR1/TR2).

Topology (TR1): one coordinator owns decomposition, delegation, aggregation, and
(in Phase 1) synthesis. Subagents are spokes — they talk only to the coordinator.

Delegation-tool recipe (verified empirically in the Phase 1 Task-0 spike, and in
memory `mar-agent-sdk-delegation`):
  - `tools=["Agent"]` gives the coordinator the delegation tool as its ONLY built-in
    (no Bash/Read/Write) — least privilege AND delegation-capable. This is the
    linchpin: `tools=[]` strips the delegation tool entirely, so a coordinator built
    that way CANNOT fan out — which is exactly `build_no_delegation_options()`, the
    permanent negative/acceptance-demo config.
  - `allowed_tools` must ALSO list the subagents' MCP tool (`mcp__research__web_search`):
    the auto-approve list is shared with subagents, so omitting it makes the subagent's
    tool calls permission-denied.
  - A subagent's distilled final result flows back inline within the same turn, so the
    coordinator can synthesize from it.
  - The research tool is served by an EXTERNAL stdio MCP server (see tools/server.py):
    an in-process SDK tool is unreliable when a subagent calls it ("Stream closed"
    control-channel races). The CLI launches the external server and both the
    coordinator and its subagents reach it directly.

Phase-1 scope: sequential delegation (parallel fan-out is Phase 2); synthesis is
coordinator-owned (no dedicated synthesis subagent yet); no refinement loop, structured
errors, or conflict/temporal handling (Phases 3–4).
"""

import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

import config
from agents.doc_analysis import doc_analysis_agent
from agents.web_search import web_search_agent
from loop import AgentRun, run_turn

_WEB_SEARCH_TOOL = f"mcp__{config.MCP_SERVER_NAME}__web_search"

#: Absolute path to the standalone stdio MCP server the CLI launches (tools/server.py).
_SERVER_SCRIPT = str(Path(__file__).resolve().parent / "tools" / "server.py")


def _research_mcp_config() -> dict:
    """External stdio MCP server config: the CLI spawns `python tools/server.py`.

    `sys.executable` is the (venv) interpreter that already has `mcp` installed; the
    server puts `src/` on its own path so it can import `config` + `mocks.corpus`.
    """
    return {
        config.MCP_SERVER_NAME: {
            "type": "stdio",
            "command": sys.executable,
            "args": [_SERVER_SCRIPT],
        }
    }

SYSTEM_PROMPT = """\
You are the lead coordinator of a multi-agent research system. Given a broad research \
question, you decompose it, delegate the legwork to specialist subagents, and \
synthesize their findings into a single cited briefing. You are the only agent that \
sees the whole picture — the subagents work in isolation and report back only to you.

How to work:
- Decompose the question into a few distinct subtopics or facets that together cover \
the whole topic — do not cover only one facet.
- Delegate the actual research using the Agent tool. You have two subagents, and you \
should use BOTH at least once:
  - `web_search`: give it ONE facet plus query hints; it searches the corpus and \
returns a distilled summary with claim->source->date lines for that facet. Use it to \
gather each facet.
  - `doc_analysis`: give it a specific document reference (id or source name) plus an \
extraction goal; it returns the claims/figures from that one document. Use it to \
CLOSELY READ at least one specific source — for example, to pin down an exact figure, \
or to compare two sources that may report different values for the same figure.
- The subagents inherit NOTHING from you. Pass everything they need explicitly in each \
delegation prompt: the subtopic, the facet, the source-type scope, and the output \
contract you expect. Never assume they can see the original question or each other's work.
- IMPORTANT — delegate SEQUENTIALLY and WAIT: send ONE subagent at a time, wait for its \
distilled results to come back, then send the next. Do NOT launch several subagents at \
once in the background. (Parallel fan-out is a later capability; for now, one at a time.)
- You MUST NOT end your turn until you have written the complete synthesized briefing. A \
message that merely says you have "launched" or "dispatched" agents and will report back \
"once they return" is NOT an acceptable final answer — keep working, collect every \
subagent's results, and only then write the briefing.
- Use what the subagents report — do not do the research yourself.
- Then synthesize ONE briefing yourself:
  - Organize it into a section per facet.
  - Every claim must carry its source and date exactly as the subagent reported them, \
written inline as `[source, date]`. Do not drop a source or invent a fact — if a claim \
has no source, it does not belong in the report.
  - Be accurate and concise. Prefer the subagents' distilled findings over your own \
prior knowledge.

Produce the final briefing as your last message.
"""


def build_coordinator_options() -> ClaudeAgentOptions:
    """The working coordinator: delegation-capable, least-privilege (TR1/TR2).

    `tools=["Agent"]` keeps ONLY the delegation tool as a built-in. `allowed_tools`
    auto-approves both the delegation tool and the subagents' `web_search` MCP tool
    (the auto-approve list is shared with subagents). `strict_mcp_config` ignores any
    ambient MCP config and uses only the in-process server passed here. `max_turns` is
    a backstop, not the expected stop reason (TR1).
    """
    return ClaudeAgentOptions(
        model=config.COORDINATOR_MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=["Agent"],
        mcp_servers=_research_mcp_config(),
        allowed_tools=["Agent", _WEB_SEARCH_TOOL],
        agents={"web_search": web_search_agent, "doc_analysis": doc_analysis_agent},
        strict_mcp_config=True,
        max_turns=config.MAX_TURNS_BACKSTOP,
    )


def build_no_delegation_options() -> ClaudeAgentOptions:
    """The negative/acceptance-demo config: a coordinator that CANNOT delegate.

    `tools=[]` strips the delegation tool (the base built-in set is empty), and no
    subagents are registered. Everything else matches the working config. Used by the
    permanent negative test: the coordinator may still answer from its own knowledge,
    but it demonstrably cannot fan out — no `Agent`/`Task` block can appear (TR2).
    """
    return ClaudeAgentOptions(
        model=config.COORDINATOR_MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        mcp_servers=_research_mcp_config(),
        allowed_tools=[_WEB_SEARCH_TOOL],
        agents={},
        strict_mcp_config=True,
        max_turns=config.MAX_TURNS_BACKSTOP,
    )


async def run_research(question: str) -> AgentRun:
    """Run one research turn end-to-end and return the structured `AgentRun`."""
    return await run_turn(question, build_coordinator_options())
