"""Agent options + system prompt.

The system prompt is scoped to BEHAVIOR and escalation judgment. It deliberately
does NOT say "always call get_customer first" — coupling a tool to every turn is
the over-trigger trap the spec warns against (CLAUDE.md). It states *when* to
verify (before order/account/financial actions), letting the model choose tools
from their descriptions (TR2).
"""

from claude_agent_sdk import ClaudeAgentOptions

import config
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
    )
