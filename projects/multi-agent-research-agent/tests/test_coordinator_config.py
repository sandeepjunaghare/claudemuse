"""Unit: coordinator option construction — the delegation-tool recipe (TR1/TR2).

These are the assertions that pin down the linchpin without spending an API call: the
working coordinator has the `Agent` delegation tool and both subagents; the negative
config strips delegation entirely. Importing `coordinator` pulls in the SDK types but
makes no API call, so these run in the default (non-integration) suite.
"""

import config
from coordinator import build_coordinator_options, build_no_delegation_options

_WEB_SEARCH_TOOL = f"mcp__{config.MCP_SERVER_NAME}__web_search"


def test_working_coordinator_can_delegate():
    o = build_coordinator_options()
    # `tools=["Agent"]` keeps ONLY the delegation tool as a built-in (linchpin).
    assert o.tools == ["Agent"]
    assert "Agent" in o.allowed_tools
    # The subagents' MCP tool must be auto-approved too (shared list) or they can't run.
    assert _WEB_SEARCH_TOOL in o.allowed_tools


def test_working_coordinator_registers_both_subagents():
    o = build_coordinator_options()
    assert set(o.agents.keys()) == {"web_search", "doc_analysis"}
    for name, agent in o.agents.items():
        assert agent.model == config.WORKER_MODEL, name  # Sonnet tier
        assert _WEB_SEARCH_TOOL in (agent.tools or []), name  # each declares its own tool
        assert config.MCP_SERVER_NAME in (agent.mcpServers or []), name


def test_coordinator_uses_opus_tier():
    assert build_coordinator_options().model == config.COORDINATOR_MODEL


def test_no_delegation_config_cannot_delegate():
    n = build_no_delegation_options()
    # `tools=[]` strips the delegation tool; no subagents registered.
    assert n.tools == []
    assert "Agent" not in (n.allowed_tools or [])
    assert not n.agents
