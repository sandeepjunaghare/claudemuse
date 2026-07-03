"""Agentic loop helper + structured run record (TR1), extended for delegation (TR1/TR2).

Mirrors the sibling `customer-support/src/loop.py`: `query()` runs the tool-use loop
internally and ends with a single `ResultMessage`; we detect termination from that
message type (never by parsing assistant text), and `terminated_by_cap` lets tests
assert the `max_turns` backstop was NOT the reason on a normal run.

Multi-agent extension: `AgentRun` also records the coordinator's **delegations** — each
`Agent`/`Task` tool-use block, with which subagent was invoked (`subagent_type`) and a
prompt excerpt — so tests assert on the fan-out *structure* (which subagents ran, how
many), never on the report's prose. The delegation tool is named `"Agent"` (renamed
from `"Task"` in Claude Code v2.1.63); we match BOTH for compatibility.

Empirical notes (Phase 1 diagnostics) — two facts that shape this loop:
  1. A subagent's messages DO stream through the parent `query()`, but carry a
     `parent_tool_use_id` (the delegating `Agent` block's id). Coordinator-level
     messages have `parent_tool_use_id is None`. We record tool calls, delegations,
     and final text ONLY from coordinator-level messages, so subagent internals stay
     isolated (TR6) and `delegations`/`tool_calls` describe the coordinator's own actions.
  2. With subagents the stream ends with MULTIPLE `ResultMessage`s — intermediate
     per-delegation announcements first, then the coordinator's real synthesis LAST.
     So we keep the LAST `ResultMessage` (overwrite as they arrive), not the first
     (the sibling's single-agent assumption would capture an announcement here).
"""

from dataclasses import dataclass, field
from typing import Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

#: Prefix the SDK applies to in-process MCP tool names: ``mcp__<server>__<tool>``.
_MCP_PREFIX_PARTS = 3

#: The delegation tool's name(s). Current SDKs emit ``"Agent"``; ``"Task"`` may still
#: appear in older streams / init tool lists — match both (see memory mar-agent-sdk-delegation).
_DELEGATION_TOOL_NAMES = ("Agent", "Task")

#: How much of a delegation prompt to retain for test/debug inspection.
_PROMPT_EXCERPT_LEN = 200


def _bare_tool_name(name: str) -> str:
    """Strip the ``mcp__<server>__`` prefix so assertions read as bare tool names."""
    if name.startswith("mcp__"):
        parts = name.split("__", _MCP_PREFIX_PARTS - 1)
        if len(parts) == _MCP_PREFIX_PARTS:
            return parts[-1]
    return name


@dataclass
class AgentRun:
    """Structured record of one agent run — the surface tests assert on.

    Assertions target tool calls, delegations, and the terminal outcome — never the
    model's prose.
    """

    tool_calls: list[str] = field(default_factory=list)  # bare tool names, in call order
    raw_tool_calls: list[str] = field(default_factory=list)  # fully-qualified names
    tool_inputs: list[dict] = field(default_factory=list)  # parsed inputs, parallel to tool_calls
    delegations: list[dict] = field(default_factory=list)  # {subagent_type, prompt_excerpt}, in order
    final_text: str = ""
    subtype: Optional[str] = None  # ResultMessage.subtype, e.g. "success" / "error_max_turns"
    stop_reason: Optional[str] = None  # ResultMessage.stop_reason if present
    is_error: bool = False
    num_turns: Optional[int] = None
    terminated_by_result: bool = False  # a ResultMessage was seen (not a torn stream)

    @property
    def terminated_by_cap(self) -> bool:
        """True if the run ended because the `max_turns` backstop was hit (TR1 anti-pattern)."""
        return bool(self.subtype and "max_turns" in self.subtype)

    @property
    def delegated_subagents(self) -> set[str]:
        """The set of subagent types the coordinator delegated to (TR2 fan-out surface)."""
        return {d["subagent_type"] for d in self.delegations if d.get("subagent_type")}


def _ingest_message(message, run: AgentRun, text_parts: list[str]) -> Optional[str]:
    """Accumulate one streamed message into `run`/`text_parts`.

    Coordinator-level messages (`parent_tool_use_id is None`) contribute tool calls,
    delegations, and final text; subagent messages (parent set) are skipped so their
    internal exploration stays isolated (TR6). Terminal metadata + the final answer are
    taken from the LAST `ResultMessage` (overwritten as they arrive) — with subagents the
    coordinator's real synthesis is the last one, after intermediate announcements.
    """
    parent = getattr(message, "parent_tool_use_id", None)

    if isinstance(message, AssistantMessage):
        if parent is not None:
            return None  # subagent-internal message — isolated (TR6), not coordinator-level
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                run.raw_tool_calls.append(block.name)
                run.tool_calls.append(_bare_tool_name(block.name))
                inp = block.input or {}
                run.tool_inputs.append(inp)
                if block.name in _DELEGATION_TOOL_NAMES:
                    run.delegations.append(
                        {
                            "subagent_type": inp.get("subagent_type"),
                            "prompt_excerpt": str(inp.get("prompt", ""))[:_PROMPT_EXCERPT_LEN],
                        }
                    )
            elif isinstance(block, TextBlock):
                if block.text:
                    text_parts.append(block.text)
    elif isinstance(message, ResultMessage):
        # Keep the LAST ResultMessage's metadata/answer (multi-agent emits several; the
        # coordinator's synthesis is last). terminated_by_result stays True once set.
        run.subtype = message.subtype
        run.stop_reason = getattr(message, "stop_reason", None)
        run.is_error = bool(message.is_error)
        run.num_turns = getattr(message, "num_turns", None)
        run.terminated_by_result = True
        if getattr(message, "result", None):
            return str(message.result)
    return None


async def run_turn(prompt: str, options: ClaudeAgentOptions) -> AgentRun:
    """Drive one agent turn to completion and return a structured `AgentRun`.

    Iterates the `query()` stream: records every tool-use block + delegation from
    assistant messages and the final assistant text, then stops on the `ResultMessage`.
    """
    run = AgentRun()
    text_parts: list[str] = []
    result_text: Optional[str] = None

    # Drain the stream to completion rather than breaking on the ResultMessage:
    # `query()` is an async generator backed by a subprocess reader, and tearing it
    # down early (via break -> aclose) while that task is live raises
    # "aclose(): asynchronous generator is already running". The ResultMessage is the
    # terminal message, so we record the first one and let iteration end naturally.
    async for message in query(prompt=prompt, options=options):
        rt = _ingest_message(message, run, text_parts)
        if rt is not None:
            result_text = rt

    # Prefer the ResultMessage's final answer; fall back to streamed text blocks.
    run.final_text = (result_text or "\n".join(text_parts)).strip()
    return run
