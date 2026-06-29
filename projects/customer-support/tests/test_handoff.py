"""Deterministic proof of the TR8 handoff core (no API).

`missing_fields` must flag every absent required field and a bad enum;
`build_summary` must produce the PRD §10 shape.
"""

from handoff import REASON_VALUES, build_summary, missing_fields

_COMPLETE = {
    "reason_for_escalation": "explicit_request",
    "root_cause": "Customer demanded a manager.",
    "recommended_action": "Call back within 1 hour.",
    "actions_taken": ["verified identity"],
    "customer": {"id": "C001", "name": "Alice Wong", "verified": True},
}


def test_complete_handoff_has_no_missing_fields():
    assert missing_fields(_COMPLETE) == []


def test_empty_actions_taken_is_allowed():
    """An immediate escalation legitimately has no prior actions — empty list is OK."""
    payload = {**_COMPLETE, "actions_taken": []}
    assert missing_fields(payload) == []


def test_flat_customer_id_accepted():
    """The customer id may be supplied flat as `customer_id` instead of nested."""
    payload = {k: v for k, v in _COMPLETE.items() if k != "customer"}
    payload["customer_id"] = "C001"
    assert missing_fields(payload) == []


def test_each_required_field_flagged_when_absent():
    for field in ("reason_for_escalation", "root_cause", "recommended_action", "actions_taken"):
        payload = {k: v for k, v in _COMPLETE.items() if k != field}
        assert field in missing_fields(payload), field


def test_missing_customer_id_flagged():
    payload = {k: v for k, v in _COMPLETE.items() if k != "customer"}
    assert "customer.id" in missing_fields(payload)


def test_actions_taken_present_but_wrong_type_flagged():
    """actions_taken must be a list; a non-list (even non-empty) is incomplete."""
    payload = {**_COMPLETE, "actions_taken": "did stuff"}
    assert "actions_taken" in missing_fields(payload)


def test_bad_enum_flagged_distinctly():
    """A present-but-invalid reason is flagged as invalid, separate from 'missing'."""
    payload = {**_COMPLETE, "reason_for_escalation": "banana"}
    missing = missing_fields(payload)
    assert "reason_for_escalation(invalid)" in missing
    assert "reason_for_escalation" not in missing  # present, just wrong


def test_all_enum_values_accepted():
    for reason in REASON_VALUES:
        assert missing_fields({**_COMPLETE, "reason_for_escalation": reason}) == []


def test_build_summary_matches_prd_shape():
    """build_summary produces the PRD §10 fields, including order when present."""
    payload = {
        **_COMPLETE,
        "order": {"id": "O1002", "status": "delivered", "amount": 900.0},
    }
    summary = build_summary(payload)
    assert summary["customer"] == {"id": "C001", "name": "Alice Wong", "verified": True}
    assert summary["order"] == {"id": "O1002", "status": "delivered", "amount": 900.0}
    assert summary["root_cause"] == "Customer demanded a manager."
    assert summary["actions_taken"] == ["verified identity"]
    assert summary["recommended_action"] == "Call back within 1 hour."
    assert summary["reason_for_escalation"] == "explicit_request"


def test_build_summary_omits_absent_order():
    """A non-order escalation (e.g. a policy gap) has no order key."""
    summary = build_summary(_COMPLETE)
    assert "order" not in summary
    assert summary["customer"]["id"] == "C001"
