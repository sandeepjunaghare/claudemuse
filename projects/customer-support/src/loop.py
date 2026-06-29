"""Agentic loop helper (TR1).

The Claude Agent SDK runs the tool-use loop internally; `query()` yields a stream
of messages and ends with a single `ResultMessage`. We satisfy TR1 *in intent*:
termination is detected from the `ResultMessage` (a message-type signal), never by
parsing assistant text for completion, and the `max_turns` cap is only a backstop —
`terminated_by_cap` lets tests assert it was NOT the reason on a normal resolution.

See project memory `cs-agent-sdk-decision` for why the SDK (not a hand-written
`stop_reason` state machine) is the chosen substrate.
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

    Assertions target tool calls and the terminal outcome, never the model's prose.
    """

    tool_calls: list[str] = field(default_factory=list)  # bare tool names, in call order
    raw_tool_calls: list[str] = field(default_factory=list)  # fully-qualified names
    tool_inputs: list[dict] = field(default_factory=list)  # parsed inputs, parallel to tool_calls
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


async def run_turn(prompt: str, options: ClaudeAgentOptions) -> AgentRun:
    """Drive one agent turn to completion and return a structured `AgentRun`.

    Iterates the `query()` stream: records every tool-use block from assistant
    messages and the final assistant text, then stops on the `ResultMessage`.
    """
    run = AgentRun()
    text_parts: list[str] = []
    result_text: Optional[str] = None

    # Drain the stream to completion rather than breaking on the ResultMessage:
    # `query()` is an async generator backed by a subprocess reader, and tearing
    # it down early (via break -> aclose) while that task is live raises
    # "aclose(): asynchronous generator is already running". The ResultMessage is
    # the terminal message, so we record the first one and let iteration end.
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    run.raw_tool_calls.append(block.name)
                    run.tool_calls.append(_bare_tool_name(block.name))
                    run.tool_inputs.append(block.input or {})
                elif isinstance(block, TextBlock):
                    if block.text:
                        text_parts.append(block.text)
        elif isinstance(message, ResultMessage) and not run.terminated_by_result:
            run.subtype = message.subtype
            run.stop_reason = getattr(message, "stop_reason", None)
            run.is_error = bool(message.is_error)
            run.num_turns = getattr(message, "num_turns", None)
            run.terminated_by_result = True
            # ResultMessage.result carries the canonical final answer when present.
            if getattr(message, "result", None):
                result_text = str(message.result)

    # Prefer the ResultMessage's final answer; fall back to streamed text blocks.
    run.final_text = (result_text or "\n".join(text_parts)).strip()
    return run
