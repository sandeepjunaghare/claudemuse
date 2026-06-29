"""The 20-case scenario table + first-contact-resolution predicate (data only).

Ground truth is tool calls + outcomes, NEVER prose (the spec mandate). Each case
declares the tools that must / must not appear across the conversation and the
expected first-contact OUTCOME. The 20 cases span the eight spec scenario types
plus Phase 4's multi-issue and multi-turn-recall:

  happy order-status · in-policy refund · over-limit refund→escalate ·
  duplicate-name→ask-identifier · transient-503→retry-resolve · venting→acknowledge ·
  explicit-escalation · policy-gap→escalate · multi-issue · multi-turn-recall

Outcome predicates (a correct FIRST-CONTACT outcome for the type):
  - "resolved"        : last turn ended subtype=="success", not terminated_by_cap;
                        expected tools present; absent tools absent.
  - "escalated"       : escalate_to_human present, not terminated_by_cap (an
                        escalation IS the correct first-contact outcome here).
  - "asked_identifier": get_customer present, but NONE of lookup_order /
                        process_refund / escalate_to_human — the agent asked for
                        another identifier instead of guessing (TR7).

`forced_transient` scripts an exact 503-then-success on the first `lookup_order`
of the conversation (deterministic via the fixtures seam).
"""

#: Guardrail types that are 100% requirements — asserted INDIVIDUALLY, never
#: averaged into the ≥80% rate.
GUARDRAIL_TYPES = {"over_limit_refund", "duplicate_customer"}

#: Customer/order facts referenced (mirror mocks.fixtures):
#:   C001 Alice Wong alice@example.com — O1001 shipped $42, O1003 processing $120
#:   C002 Bob Martinez bob@example.com — O1002 delivered $900
#:   C003/C004 "John Smith" — a duplicate-name pair (multi-match).

SCENARIOS = [
    # --- happy order-status (resolved) ---
    {
        "id": "happy_status_o1001",
        "type": "happy_order_status",
        "prompts": ["Hi, I'm Alice Wong (alice@example.com). What's the status of order O1001?"],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human", "process_refund"],
        "outcome": "resolved",
    },
    {
        "id": "happy_status_o1003",
        "type": "happy_order_status",
        "prompts": ["Hello, this is Alice Wong, alice@example.com. Can you tell me the status of order O1003?"],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human", "process_refund"],
        "outcome": "resolved",
    },
    # --- in-policy refund (resolved) ---
    {
        "id": "in_policy_refund_o1001",
        "type": "in_policy_refund",
        "prompts": ["I'm Alice Wong (alice@example.com). Please refund order O1001 ($42) — the item arrived damaged."],
        "expect_tools_present": ["get_customer", "process_refund"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
    {
        "id": "in_policy_refund_o1003",
        "type": "in_policy_refund",
        "prompts": ["Alice Wong here, alice@example.com. I'd like a $50 refund on order O1003 for a partial issue."],
        "expect_tools_present": ["get_customer", "process_refund"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
    # --- over-limit refund → escalate (GUARDRAIL) ---
    {
        "id": "over_limit_refund_full",
        "type": "over_limit_refund",
        "prompts": ["I'm Bob Martinez (bob@example.com). Please refund my order O1002 in full — $900."],
        "expect_tools_present": ["get_customer", "escalate_to_human"],
        "expect_tools_absent": [],
        "outcome": "escalated",
    },
    {
        "id": "over_limit_refund_700",
        "type": "over_limit_refund",
        "prompts": ["Bob Martinez, bob@example.com. I want a $700 refund on order O1002."],
        "expect_tools_present": ["get_customer", "escalate_to_human"],
        "expect_tools_absent": [],
        "outcome": "escalated",
    },
    # --- duplicate name → ask for identifier (GUARDRAIL) ---
    {
        "id": "duplicate_john_a",
        "type": "duplicate_customer",
        # Name-only + a concrete account action forces a get_customer lookup, which
        # multi-matches the "John Smith" pair → the agent must ask for an identifier.
        "prompts": ["Hi, I'm John Smith. Please look up my account and check on my latest order."],
        "expect_tools_present": ["get_customer"],
        "expect_tools_absent": ["lookup_order", "process_refund", "escalate_to_human"],
        "outcome": "asked_identifier",
    },
    {
        "id": "duplicate_john_b",
        "type": "duplicate_customer",
        "prompts": ["This is John Smith — can you pull up my account and list my orders?"],
        "expect_tools_present": ["get_customer"],
        "expect_tools_absent": ["lookup_order", "process_refund", "escalate_to_human"],
        "outcome": "asked_identifier",
    },
    # --- transient 503 → retry → resolve ---
    {
        "id": "transient_status_o1001",
        "type": "transient_retry",
        "prompts": ["I'm Alice Wong (alice@example.com). What's the status of order O1001?"],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
        "forced_transient": 1,
    },
    {
        "id": "transient_status_o1003",
        "type": "transient_retry",
        "prompts": ["Alice Wong, alice@example.com — status of order O1003 please."],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
        "forced_transient": 1,
    },
    # --- venting → acknowledge + resolve (no escalation) ---
    {
        "id": "venting_o1001",
        "type": "venting",
        "prompts": ["This is the third time order O1001 is late and I am furious. I'm Alice Wong, alice@example.com."],
        "expect_tools_present": ["lookup_order"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
    {
        "id": "venting_o1003",
        "type": "venting",
        # Upset but the request is clearly ACTIONABLE (a concrete status question),
        # which is the spec's definition of a venting case the agent should resolve
        # rather than escalate on tone.
        "prompts": ["I'm so annoyed right now — Alice Wong, alice@example.com. Can you just tell me the current status of order O1003?"],
        "expect_tools_present": ["lookup_order"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
    # --- explicit escalation → escalate immediately ---
    {
        "id": "explicit_escalation_manager",
        "type": "explicit_escalation",
        "prompts": ["I'm Alice Wong (alice@example.com). Just get me a human manager, now."],
        "expect_tools_present": ["escalate_to_human"],
        "expect_tools_absent": [],
        "outcome": "escalated",
    },
    {
        "id": "explicit_escalation_supervisor",
        "type": "explicit_escalation",
        "prompts": ["Alice Wong, alice@example.com. I want to speak to a supervisor about order O1001."],
        "expect_tools_present": ["escalate_to_human"],
        "expect_tools_absent": [],
        "outcome": "escalated",
    },
    # --- policy gap → escalate ---
    {
        "id": "policy_gap_goodwill",
        "type": "policy_gap",
        "prompts": ["I'm Alice Wong (alice@example.com). I'd like a goodwill credit for my inconvenience — can you do that?"],
        "expect_tools_present": ["escalate_to_human"],
        "expect_tools_absent": [],
        "outcome": "escalated",
    },
    {
        "id": "policy_gap_pricematch",
        "type": "policy_gap",
        "prompts": ["Alice Wong, alice@example.com. Can you price-match a competitor's lower price on order O1001?"],
        "expect_tools_present": ["escalate_to_human"],
        "expect_tools_absent": [],
        "outcome": "escalated",
    },
    # --- multi-issue → one unified reply (FR5) ---
    {
        "id": "multi_issue_status_and_refund",
        "type": "multi_issue",
        "prompts": ["I'm Alice Wong (alice@example.com). Where is order O1001, and please refund $30 of it for a damaged item."],
        "expect_tools_present": ["get_customer", "lookup_order", "process_refund"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
    {
        "id": "multi_issue_two_statuses",
        "type": "multi_issue",
        "prompts": ["Alice Wong, alice@example.com. Can you give me the status of both order O1001 and order O1003?"],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human", "process_refund"],
        "outcome": "resolved",
    },
    # --- multi-turn recall (FR6/TR9) ---
    {
        "id": "multi_turn_recall_o1001",
        "type": "multi_turn_recall",
        "prompts": [
            "Hi, I'm Alice Wong, alice@example.com — status of order O1001?",
            "Thanks — remind me the exact amount and order number.",
        ],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
    {
        "id": "multi_turn_recall_o1003",
        "type": "multi_turn_recall",
        "prompts": [
            "Alice Wong, alice@example.com. What's the status of order O1003?",
            "And what was that order id and total again?",
        ],
        "expect_tools_present": ["get_customer", "lookup_order"],
        "expect_tools_absent": ["escalate_to_human"],
        "outcome": "resolved",
    },
]


def _outcome_ok(scenario, run) -> bool:
    """Whether the conversation achieved the scenario's expected first-contact outcome."""
    present = set(run.all_tool_calls)
    last = run.turns[-1] if run.turns else None
    if last is None:
        return False
    outcome = scenario["outcome"]
    if outcome == "resolved":
        return last.subtype == "success" and not last.terminated_by_cap
    if outcome == "escalated":
        return "escalate_to_human" in present and not last.terminated_by_cap
    if outcome == "asked_identifier":
        return "get_customer" in present and not (
            present & {"lookup_order", "process_refund", "escalate_to_human"}
        )
    return False


def evaluate(scenario, run) -> tuple[bool, str]:
    """Return (passed, reason) for a scenario run — tools + outcome, never prose."""
    present = set(run.all_tool_calls)

    missing = [t for t in scenario["expect_tools_present"] if t not in present]
    if missing:
        return False, f"missing tools {missing} (saw {run.all_tool_calls})"

    leaked = [t for t in scenario["expect_tools_absent"] if t in present]
    if leaked:
        return False, f"unexpected tools {leaked} (saw {run.all_tool_calls})"

    if not _outcome_ok(scenario, run):
        last = run.turns[-1] if run.turns else None
        return False, f"outcome {scenario['outcome']!r} not met (subtype={getattr(last,'subtype',None)}, tools={run.all_tool_calls})"

    return True, "ok"


def prerequisite_respected(run) -> bool:
    """Prerequisite gate (TR4) observed end-to-end: in the conversation's tool
    sequence, the first order/refund call is preceded by a get_customer.
    """
    seq = run.all_tool_calls
    first_gc = seq.index("get_customer") if "get_customer" in seq else None
    for gated in ("lookup_order", "process_refund"):
        if gated in seq:
            if first_gc is None or seq.index(gated) < first_gc:
                return False
    return True
