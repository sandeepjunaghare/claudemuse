"""Agent options + system prompt.

The system prompt is scoped to BEHAVIOR and escalation judgment. It deliberately
does NOT say "always call get_customer first" — coupling a tool to every turn is
the over-trigger trap the spec warns against (CLAUDE.md). It states *when* to
verify (before order/account/financial actions), letting the model choose tools
from their descriptions (TR2).
"""

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

import config
from hooks.normalize import normalize_order_dates
from hooks.prerequisite_gate import prerequisite_gate, record_verified_customer
from hooks.refund_gate import refund_gate
from tools.server import support_server

#: Fully-qualified tool names for least-privilege scoping (D2.3).
ALLOWED_TOOLS = [
    f"mcp__{config.MCP_SERVER_NAME}__get_customer",
    f"mcp__{config.MCP_SERVER_NAME}__lookup_order",
    f"mcp__{config.MCP_SERVER_NAME}__process_refund",
    f"mcp__{config.MCP_SERVER_NAME}__escalate_to_human",
]

SYSTEM_PROMPT = """\
You are a customer support resolution agent for a mid-size online retailer. You \
help customers with order status, returns and refunds, billing disputes, and \
account updates, resolving what you safely can in a single contact.

How to work:
- Verify the customer's identity before any operation that touches an order, an \
account, or money (order lookups, refunds, account changes). Identity is \
established with the customer-identification tool, which returns a verified \
customer id that the order and refund tools require. You do not need to verify \
for general questions that don't touch a specific account.
- If customer identification returns more than one matching person, ask the \
customer for an additional identifier (such as email or order number) to confirm \
who they are. Never guess between multiple matches.
- Refunds may only be issued within standard policy. Larger or out-of-policy \
refunds are not something you can do yourself — route them to a human.
- Escalate to a human when the customer explicitly asks for one, when policy is \
silent or ambiguous, or when you genuinely cannot make progress.

Be concise, accurate, and friendly. When you have resolved the request, give the \
customer a clear, direct answer.
"""


def _build_hooks() -> dict:
    """Wire the Phase 2 deterministic guardrails as SDK hooks (TR3/TR4/TR5).

    These enforce the invariants in code — NOT in the system prompt (the
    deterministic-vs-probabilistic thesis, CLAUDE.md). The matchers scope each
    hook to its tool(s); the hooks ALSO re-check the tool name internally, so
    matcher semantics are an optimization, not a correctness dependency.
    """
    refund = f"mcp__{config.MCP_SERVER_NAME}__process_refund"
    order = f"mcp__{config.MCP_SERVER_NAME}__lookup_order"
    customer = f"mcp__{config.MCP_SERVER_NAME}__get_customer"
    return {
        "PreToolUse": [
            # TR4: gate order/refund actions behind a verified customer.
            HookMatcher(matcher=f"{order}|{refund}", hooks=[prerequisite_gate]),
            # TR3: deny over-limit refunds (block is the 100% guarantee).
            HookMatcher(matcher=refund, hooks=[refund_gate]),
        ],
        "PostToolUse": [
            # TR4 writer: record the verified customer id on a single match.
            HookMatcher(matcher=customer, hooks=[record_verified_customer]),
            # TR5: normalize the order date to ISO 8601 before the model reads it.
            HookMatcher(matcher=order, hooks=[normalize_order_dates]),
        ],
    }


def build_options() -> ClaudeAgentOptions:
    """Construct the agent's run options (least-privilege, behavior-focused).

    `tools=[]` strips the CLI's built-in tools (Bash, Read, Write, ...) so the
    agent's entire toolset is the four MCP tools below — true least privilege
    (D2.3). It also keeps the tool registry small enough that the CLI does not
    defer tools behind a ToolSearch discovery step, so the agent sees all four
    tools upfront. `strict_mcp_config` ignores any ambient MCP configuration and
    uses only the in-process server we pass here.
    """
    return ClaudeAgentOptions(
        model=config.MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        mcp_servers={config.MCP_SERVER_NAME: support_server},
        allowed_tools=ALLOWED_TOOLS,
        strict_mcp_config=True,
        max_turns=config.MAX_TURNS_BACKSTOP,
        hooks=_build_hooks(),
    )
