"""Unit: coordinator option construction — the delegation-tool recipe (TR1/TR2).

These are the assertions that pin down the linchpin without spending an API call: the
working coordinator has the `Agent` delegation tool and both subagents; the negative
config strips delegation entirely. Importing `coordinator` pulls in the SDK types but
makes no API call, so these run in the default (non-integration) suite.
"""

import config
from coordinator import (
    SYSTEM_PROMPT,
    build_coordinator_options,
    build_no_delegation_options,
    build_partial_coordinator_options,
    build_sequential_coordinator_options,
    build_single_agent_options,
)

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


def test_subagents_run_in_background_for_parallel_overlap():
    # Phase-2 spike decision (Path B): background=True is what makes back-to-back
    # delegations overlap in wall-clock (peak_concurrent_tasks >= 2 / TR2).
    o = build_coordinator_options()
    for name, agent in o.agents.items():
        assert agent.background is True, name


def test_single_agent_fallback_cannot_delegate_but_keeps_web_search():
    # The cheap narrow-lookup path (TR3/TR10): no Agent tool, no subagents, Sonnet tier,
    # but web_search still reachable so it answers the fact directly.
    s = build_single_agent_options()
    assert s.tools == []
    assert "Agent" not in (s.allowed_tools or [])
    assert not s.agents
    assert s.model == config.WORKER_MODEL
    assert _WEB_SEARCH_TOOL in s.allowed_tools


def test_sequential_baseline_matches_parallel_except_the_prompt():
    # The benchmark baseline: same delegation-capable config, only the system prompt differs.
    seq = build_sequential_coordinator_options()
    par = build_coordinator_options()
    assert seq.tools == ["Agent"]
    assert set(seq.agents.keys()) == {"web_search", "doc_analysis"}
    assert _WEB_SEARCH_TOOL in seq.allowed_tools
    assert seq.system_prompt != par.system_prompt  # distinct steering


def test_partial_coordinator_delegates_but_under_covers():
    # Phase-3 gap fixture (TR5): delegation-capable in every way the full coordinator is,
    # but a distinct, deliberately under-covering system prompt.
    p = build_partial_coordinator_options()
    assert p.tools == ["Agent"]
    assert set(p.agents.keys()) == {"web_search", "doc_analysis"}
    assert _WEB_SEARCH_TOOL in p.allowed_tools
    assert p.system_prompt != build_coordinator_options().system_prompt


def test_system_prompt_carries_coverage_and_partitioning_contract():
    # TR4: the coordinator is asked to partition facets and emit a machine-readable block.
    assert "COVERAGE:" in SYSTEM_PROMPT
    assert "one facet" in SYSTEM_PROMPT.lower()
