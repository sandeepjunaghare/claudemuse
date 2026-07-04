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

Phase-2 extension (parallelism + cost, TR2/TR3/TR10):

  Parallelism proof — decided by the Phase-2 spike (memory `mar-agent-sdk-delegation`):
  the Opus coordinator does NOT emit multiple `Agent` blocks in one assistant message
  under ANY `background` setting — it fires one `Agent` call per message. So
  `max_parallel_delegations` (max delegations in a single message) is instrumentation of
  the model's tool-call *batching intent*, and is 1 in practice — NOT the parallelism
  signal. Real concurrency instead comes from `background=True` subagents: fired
  back-to-back, their background tasks OVERLAP in wall-clock (the spike measured 5 active
  at once). `peak_concurrent_tasks` replays the ordered `task_events` (a `started` opens a
  task, a terminal status closes it) to measure that overlap — THAT is the deterministic
  TR2/FR3 proof, and `fanned_out_in_parallel` (`>= 2`) is the acceptance property.

  `task_events` records the four `Task*Message` lifecycle types (per-task `total_tokens`/
  `duration_ms` from `TaskUsage`); `total_cost_usd`/`usage` come from the final
  `ResultMessage`, so tests and `run_example.py` can account for the ~15× multi-agent cost
  (TR10). `route` is stamped by `run_research()` after the turn (the loop is route-agnostic).
"""

from dataclasses import dataclass, field
from typing import Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    TERMINAL_TASK_STATUSES,
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

#: Maps each `Task*Message` type to the `kind` string recorded in `task_events`.
_TASK_EVENT_KINDS = {
    TaskStartedMessage: "started",
    TaskProgressMessage: "progress",
    TaskNotificationMessage: "notification",
    TaskUpdatedMessage: "updated",
}


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
    delegation_batches: list[list[str]] = field(default_factory=list)  # one list per coordinator msg with ≥1 delegation
    task_events: list[dict] = field(default_factory=list)  # one dict per Task*Message (lifecycle + usage)
    route: Optional[str] = None  # set by run_research() (triage route), not by the loop
    final_text: str = ""
    subtype: Optional[str] = None  # ResultMessage.subtype, e.g. "success" / "error_max_turns"
    stop_reason: Optional[str] = None  # ResultMessage.stop_reason if present
    is_error: bool = False
    num_turns: Optional[int] = None
    total_cost_usd: Optional[float] = None  # ResultMessage.total_cost_usd (TR10 cost accounting)
    usage: Optional[dict] = None  # ResultMessage.usage (TR10 token accounting)
    terminated_by_result: bool = False  # a ResultMessage was seen (not a torn stream)

    @property
    def terminated_by_cap(self) -> bool:
        """True if the run ended because the `max_turns` backstop was hit (TR1 anti-pattern)."""
        return bool(self.subtype and "max_turns" in self.subtype)

    @property
    def delegated_subagents(self) -> set[str]:
        """The set of subagent types the coordinator delegated to (TR2 fan-out surface)."""
        return {d["subagent_type"] for d in self.delegations if d.get("subagent_type")}

    @property
    def max_parallel_delegations(self) -> int:
        """The most subagents delegated in a SINGLE coordinator message (batching INTENT).

        NOTE: instrumentation, NOT the parallelism proof. The Phase-2 spike showed the
        coordinator emits one `Agent` call per message under every `background` setting,
        so this is 1 in practice. Real concurrency is measured by `peak_concurrent_tasks`.
        """
        return max((len(b) for b in self.delegation_batches), default=0)

    @property
    def peak_concurrent_tasks(self) -> int:
        """Peak number of subagent tasks active at once — the TR2/FR3 concurrency proof.

        Replays the ordered `task_events`: a `started` event opens a task, the first
        terminal status (`completed`/`failed`/`stopped`/`killed`, from a notification OR an
        updated patch) closes it. `background=True` subagents fired back-to-back overlap, so
        this reaches ≥2 even though each was delegated in its own message. A task may emit
        BOTH a terminal notification and a terminal update — `discard` makes the close
        idempotent so it is counted once.
        """
        active: set = set()
        peak = 0
        for event in self.task_events:
            task_id = event.get("task_id")
            if task_id is None:
                continue
            if event.get("kind") == "started":
                active.add(task_id)
                peak = max(peak, len(active))
            elif event.get("status") in TERMINAL_TASK_STATUSES:
                active.discard(task_id)
        return peak

    @property
    def fanned_out_in_parallel(self) -> bool:
        """True iff ≥2 subagent tasks ran concurrently — the acceptance signal (TR2/FR3)."""
        return self.peak_concurrent_tasks >= 2

    @property
    def subagent_total_tokens(self) -> int:
        """Total tokens reported by subagents via `task_notification` events (TR10 cost).

        Sums `total_tokens` across `notification` task_events (their terminal usage);
        0 when the run returned subagent results inline (Path A) without task lifecycle
        events, in which case the coordinator's own `usage` reflects the whole run.
        """
        return sum(
            e["total_tokens"] or 0
            for e in self.task_events
            if e.get("kind") == "notification"
        )


def _task_event(message) -> dict:
    """Flatten one `Task*Message` into the `task_events` record shape.

    `TaskUsage` is a TypedDict (`{total_tokens, tool_uses, duration_ms}`) accessed by
    subscript; it is `None` on some notifications and absent entirely on started/updated,
    so pull defensively. Terminal status may arrive on EITHER a notification or an
    updated patch — record `.status` from whichever carries it.
    """
    usage = getattr(message, "usage", None)
    return {
        "kind": _TASK_EVENT_KINDS.get(type(message)),
        "task_id": getattr(message, "task_id", None),
        "tool_use_id": getattr(message, "tool_use_id", None),
        "status": getattr(message, "status", None),
        "total_tokens": usage["total_tokens"] if usage else None,
        "duration_ms": usage["duration_ms"] if usage else None,
    }


def _ingest_message(message, run: AgentRun, text_parts: list[str]) -> Optional[str]:
    """Accumulate one streamed message into `run`/`text_parts`.

    Coordinator-level messages (`parent_tool_use_id is None`) contribute tool calls,
    delegations, and final text; subagent messages (parent set) are skipped so their
    internal exploration stays isolated (TR6). Terminal metadata + the final answer are
    taken from the LAST `ResultMessage` (overwritten as they arrive) — with subagents the
    coordinator's real synthesis is the last one, after intermediate announcements.

    `Task*Message`s are the background-run lifecycle mechanism (not subagent-internal
    tool calls), so they are recorded regardless of `parent_tool_use_id` — matched
    explicitly BEFORE any generic system handling.
    """
    # Task lifecycle events first — they are SystemMessage subclasses and NOT gated on
    # parent_tool_use_id (they describe delegated tasks, not coordinator tool calls).
    if type(message) in _TASK_EVENT_KINDS:
        run.task_events.append(_task_event(message))
        return None

    parent = getattr(message, "parent_tool_use_id", None)

    if isinstance(message, AssistantMessage):
        if parent is not None:
            return None  # subagent-internal message — isolated (TR6), not coordinator-level
        batch: list[str] = []  # subagent_types delegated in THIS single message (parallel signal)
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                run.raw_tool_calls.append(block.name)
                run.tool_calls.append(_bare_tool_name(block.name))
                inp = block.input or {}
                run.tool_inputs.append(inp)
                if block.name in _DELEGATION_TOOL_NAMES:
                    subagent_type = inp.get("subagent_type")
                    run.delegations.append(
                        {
                            "subagent_type": subagent_type,
                            "prompt_excerpt": str(inp.get("prompt", ""))[:_PROMPT_EXCERPT_LEN],
                        }
                    )
                    batch.append(subagent_type)
            elif isinstance(block, TextBlock):
                if block.text:
                    text_parts.append(block.text)
        # One batch per coordinator message that delegated: len(batch) >= 2 ⇒ parallel fan-out.
        if batch:
            run.delegation_batches.append(batch)
    elif isinstance(message, ResultMessage):
        # Keep the LAST ResultMessage's metadata/answer (multi-agent emits several; the
        # coordinator's synthesis is last). terminated_by_result stays True once set.
        run.subtype = message.subtype
        run.stop_reason = getattr(message, "stop_reason", None)
        run.is_error = bool(message.is_error)
        run.num_turns = getattr(message, "num_turns", None)
        run.total_cost_usd = getattr(message, "total_cost_usd", None)
        run.usage = getattr(message, "usage", None)
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
