"""Multi-turn conversation driver (Phase 4 substrate).

`loop.run_turn` drives a single one-shot `query()`, which starts a FRESH session
every call — fine for the per-turn Phase 1-3 tests, but with no continuity it
cannot carry case facts across turns, exercise venting→reiteration→escalate, or
measure a multi-turn resolution rate. This module adds the persistent substrate:
`run_conversation` opens ONE `ClaudeSDKClient` session and sends each prompt on
it, so all turns share history AND the same `session_id` — which is what keys
`verified_store` and `case_facts` consistently across the conversation, and is
what lets the case-facts inject hook re-supply facts recorded on turn N into
turn N+1's prompt.

Message ingest is the SHARED `loop._ingest_message`, so tool-call/text/result
parsing is identical to `run_turn`. Task 0 confirmed (sdk 0.2.110):
`ClaudeSDKClient` supports `async with`, multiple `query()` calls continue one
conversation, hooks fire in client mode, and `receive_response()` self-terminates
at the `ResultMessage` (so we never `break` — the Phase 1 `aclose()` race).
"""

from dataclasses import dataclass, field

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from loop import AgentRun, _ingest_message


@dataclass
class TurnRecord:
    """One turn of a conversation. Wraps an `AgentRun` for the per-turn body so the
    assert surface (tool calls, subtype, terminated_by_cap, ...) is identical to
    the one-shot driver, and adds the `prompt` that produced it.
    """

    prompt: str
    _run: AgentRun = field(default_factory=AgentRun)
    final_text: str = ""

    @property
    def tool_calls(self) -> list[str]:
        return self._run.tool_calls

    @property
    def raw_tool_calls(self) -> list[str]:
        return self._run.raw_tool_calls

    @property
    def tool_inputs(self) -> list[dict]:
        return self._run.tool_inputs

    @property
    def subtype(self):
        return self._run.subtype

    @property
    def stop_reason(self):
        return self._run.stop_reason

    @property
    def is_error(self) -> bool:
        return self._run.is_error

    @property
    def num_turns(self):
        return self._run.num_turns

    @property
    def terminated_by_result(self) -> bool:
        return self._run.terminated_by_result

    @property
    def terminated_by_cap(self) -> bool:
        return self._run.terminated_by_cap


@dataclass
class ConversationRun:
    """A whole multi-turn conversation — the surface the multi-turn tests assert on."""

    turns: list[TurnRecord] = field(default_factory=list)

    @property
    def all_tool_calls(self) -> list[str]:
        """Every turn's tool calls, flattened in conversation order."""
        return [name for turn in self.turns for name in turn.tool_calls]

    @property
    def final_text(self) -> str:
        """The last turn's final answer (``""`` if the conversation was empty)."""
        return self.turns[-1].final_text if self.turns else ""


async def run_conversation(prompts: list[str], options: ClaudeAgentOptions) -> ConversationRun:
    """Drive `prompts` as ONE continuous conversation and return a `ConversationRun`.

    Opens a single `ClaudeSDKClient` (Task 0: `async with` is supported); each
    prompt is sent on the same default `session_id`, so history, `verified_store`,
    and `case_facts` are all shared across turns. Per turn we drain
    `receive_response()` (which ends at the `ResultMessage`) through the shared
    `_ingest_message`, never breaking early.
    """
    run = ConversationRun(turns=[])
    async with ClaudeSDKClient(options=options) as client:
        for prompt in prompts:
            await client.query(prompt)  # default session_id => one conversation
            turn = TurnRecord(prompt=prompt)
            text_parts: list[str] = []
            result_text = None
            async for message in client.receive_response():
                rt = _ingest_message(message, turn._run, text_parts)
                if rt is not None:
                    result_text = rt
            turn.final_text = (result_text or "\n".join(text_parts)).strip()
            run.turns.append(turn)
    return run
