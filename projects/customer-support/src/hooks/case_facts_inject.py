"""Case-facts injector (TR9a): a UserPromptSubmit hook that prepends the
session's rendered case-facts block to every prompt via `additionalContext`.

Because the block is rebuilt from `context.case_facts` on EVERY prompt (not
recalled from conversation history), the exact figures are structurally immune
to history summarization — a `/compact` cannot drop or paraphrase them. This is
the deterministic-vs-probabilistic thesis applied to context hygiene: the facts
ride in code-controlled `additionalContext`, never as a model recollection.

Task-0 finding (claude-agent-sdk 0.2.110, verified this phase): a UserPromptSubmit
hook returning `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
"additionalContext": <str>}}` DOES reach the model — the smoke driver had the
model echo an injected `SECRET_TOKEN`. So `additionalContext` is the delivery
mechanism; the prepend-in-driver fallback was NOT needed. (The UserPromptSubmit
input carries `session_id`/`prompt` but no `tool_name`; the callback's
`tool_use_id` arg is unused here.)

Returning `{}` on an empty store is what keeps single-shot `query()` runs (the
Phase 1-3 tests) regression-free: the first prompt of any conversation, before
any tool has run, injects nothing.
"""

from context import case_facts


async def case_facts_inject(input: dict, tool_use_id, context) -> dict:
    """UserPromptSubmit hook: inject the case-facts block as `additionalContext` (TR9a)."""
    block = case_facts.render_block(input.get("session_id", ""))
    if not block:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": block,
        }
    }
