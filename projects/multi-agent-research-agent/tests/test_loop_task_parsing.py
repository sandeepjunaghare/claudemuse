"""Unit tests for the Phase-2 loop instrumentation (TR2/TR6/TR10). No API call.

Drives `loop._ingest_message` directly with synthetic SDK messages to verify the
parallelism/cost signals WITHOUT a live run:
  - delegation batching is recorded per coordinator message (`delegation_batches` /
    `max_parallel_delegations`) — instrumentation of the model's tool-call intent;
  - REAL parallelism is `peak_concurrent_tasks` (≥2 tasks active at once) computed from an
    ordered `task_events` timeline — the acceptance signal decided by the Phase-2 spike,
    because the coordinator fires one `Agent` call per message (so `max_parallel_delegations`
    stays 1 live) but `background=True` subagent tasks OVERLAP;
  - a `TaskNotificationMessage` with usage → a `notification` task_event + subagent tokens;
  - a `TaskUpdatedMessage` with a terminal `killed` status → recorded, status is terminal;
  - a subagent-internal `AssistantMessage` (`parent_tool_use_id` set) → IGNORED (TR6).

Constructing SDK dataclasses imports the SDK but makes NO network call, so this stays in
the default (non-integration) suite — precedent: `test_coordinator_config.py`.
"""

from claude_agent_sdk import (
    AssistantMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    TERMINAL_TASK_STATUSES,
    TextBlock,
    ToolUseBlock,
)

import loop


def _ingest(messages):
    """Run a list of synthetic messages through a fresh AgentRun; return it."""
    run = loop.AgentRun()
    text_parts: list[str] = []
    for m in messages:
        loop._ingest_message(m, run, text_parts)
    return run


def _agent_block(subagent_type, block_id):
    return ToolUseBlock(id=block_id, name="Agent", input={"subagent_type": subagent_type, "prompt": "do X"})


def _started(task_id):
    return TaskStartedMessage(
        subtype="task_started", data={}, task_id=task_id,
        description="d", uuid="u", session_id="s",
    )


def _completed(task_id, total_tokens=None):
    usage = None if total_tokens is None else {"total_tokens": total_tokens, "tool_uses": 1, "duration_ms": 10}
    return TaskNotificationMessage(
        subtype="task_notification", data={}, task_id=task_id, status="completed",
        output_file="", summary="done", uuid="u", session_id="s", usage=usage,
    )


def test_multiple_agent_blocks_in_one_message_records_a_batch():
    # Batching intent is recorded even though the LIVE coordinator never does this — it is
    # instrumentation, not the parallelism proof (see peak_concurrent_tasks below).
    msg = AssistantMessage(
        content=[_agent_block("web_search", "t1"), _agent_block("doc_analysis", "t2")],
        model="claude-opus-4-8",
        parent_tool_use_id=None,
    )
    run = _ingest([msg])

    assert run.delegation_batches == [["web_search", "doc_analysis"]]
    assert run.max_parallel_delegations == 2
    # No task events → no measured concurrency, so NOT fanned out (the acceptance signal is
    # task overlap, not message batching).
    assert run.peak_concurrent_tasks == 0
    assert run.fanned_out_in_parallel is False
    # The existing per-delegation surface is unchanged.
    assert len(run.delegations) == 2
    assert run.delegated_subagents == {"web_search", "doc_analysis"}
    assert run.tool_calls == ["Agent", "Agent"]


def test_one_agent_block_per_message_still_records_each_delegation():
    m1 = AssistantMessage(content=[_agent_block("web_search", "a")], model="m", parent_tool_use_id=None)
    m2 = AssistantMessage(content=[_agent_block("doc_analysis", "b")], model="m", parent_tool_use_id=None)
    run = _ingest([m1, m2])

    assert run.delegation_batches == [["web_search"], ["doc_analysis"]]
    assert run.max_parallel_delegations == 1  # the LIVE shape — one Agent call per message
    assert run.delegated_subagents == {"web_search", "doc_analysis"}


def test_overlapping_background_tasks_prove_parallelism():
    # Two tasks start before either completes → peak concurrency 2 (the real TR2/FR3 proof).
    run = _ingest([
        _started("task-a"),
        _started("task-b"),
        _completed("task-a"),
        _completed("task-b"),
    ])
    assert run.peak_concurrent_tasks == 2
    assert run.fanned_out_in_parallel is True


def test_sequential_tasks_are_not_parallel():
    # Each task completes before the next starts → peak concurrency 1 (never overlapped).
    run = _ingest([
        _started("task-a"),
        _completed("task-a"),
        _started("task-b"),
        _completed("task-b"),
    ])
    assert run.peak_concurrent_tasks == 1
    assert run.fanned_out_in_parallel is False


def test_double_terminal_event_closes_task_once():
    # A task may emit BOTH a terminal notification and a terminal update; the close must be
    # idempotent so a stale decrement can't understate a later peak.
    run = _ingest([
        _started("task-a"),
        _completed("task-a"),                                  # notification terminal
        TaskUpdatedMessage(subtype="task_updated", data={}, task_id="task-a",
                           patch={"status": "completed"}, status="completed"),  # duplicate terminal
        _started("task-b"),
        _started("task-c"),
    ])
    # task-a is closed once; b and c overlap → peak 2, not corrupted by the double-close.
    assert run.peak_concurrent_tasks == 2


def test_task_notification_records_event_and_tokens():
    note = TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id="task-1",
        status="completed",
        output_file="/tmp/out.txt",
        summary="distilled result",
        uuid="u1",
        session_id="s1",
        tool_use_id="t1",
        usage={"total_tokens": 1234, "tool_uses": 3, "duration_ms": 5000},
    )
    run = _ingest([note])

    assert len(run.task_events) == 1
    ev = run.task_events[0]
    assert ev["kind"] == "notification"
    assert ev["task_id"] == "task-1"
    assert ev["total_tokens"] == 1234
    assert ev["duration_ms"] == 5000
    assert run.subagent_total_tokens == 1234


def test_task_notification_without_usage_is_defensive():
    note = TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id="task-2",
        status="completed",
        output_file="",
        summary="",
        uuid="u2",
        session_id="s2",
        usage=None,  # usage may be absent — must not crash
    )
    run = _ingest([note])

    assert run.task_events[0]["total_tokens"] is None
    assert run.task_events[0]["duration_ms"] is None
    assert run.subagent_total_tokens == 0  # a None-token notification contributes 0


def test_task_updated_terminal_status_recorded():
    upd = TaskUpdatedMessage(
        subtype="task_updated",
        data={},
        task_id="task-3",
        patch={"status": "killed"},
        status="killed",
    )
    run = _ingest([upd])

    assert len(run.task_events) == 1
    ev = run.task_events[0]
    assert ev["kind"] == "updated"
    assert ev["status"] == "killed"
    assert ev["status"] in TERMINAL_TASK_STATUSES


def test_subagent_internal_message_is_ignored():
    # A subagent's own tool call carries parent_tool_use_id — it must NOT leak into the
    # coordinator's tool_calls / batches (TR6 isolation).
    internal = AssistantMessage(
        content=[ToolUseBlock(id="x", name="mcp__research__web_search", input={"query": "q"})],
        model="claude-sonnet-4-6",
        parent_tool_use_id="parent-tool-abc",
    )
    run = _ingest([internal])

    assert run.tool_calls == []
    assert run.delegation_batches == []
    assert run.max_parallel_delegations == 0
