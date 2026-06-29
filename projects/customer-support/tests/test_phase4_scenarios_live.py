"""The 20-case resolution-rate gate (live API) — the headline acceptance test.

Runs every scenario in `scenarios.SCENARIOS` through the multi-turn driver and
measures first-contact resolution as GROUND TRUTH (tool calls + outcomes, never
prose). Two assertions:
  (a) resolution rate ≥ 0.80 across all cases (the spec acceptance target);
  (b) every GUARDRAIL case (over-limit refund, duplicate-name) passes its hard
      predicate individually — these are 100% requirements, not averaged in —
      plus the prerequisite gate is observed in every conversation.

All 20 scenarios run inside this one test, so stores are reset BETWEEN scenarios
explicitly (the autouse fixtures only fire per-test). Run with `-s` to see the
per-scenario table.
"""

import shutil

import pytest

import config
from context import case_facts
from hooks import verified_store
from mocks import fixtures
from scenarios import GUARDRAIL_TYPES, SCENARIOS, evaluate, prerequisite_respected

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _runnable, reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run."),
]

#: The minimum acceptable first-contact resolution rate (spec acceptance criterion).
_RESOLUTION_TARGET = 0.80


def _reset_between_scenarios():
    """Isolate each scenario: clear both session stores + the flaky seam."""
    verified_store.reset()
    case_facts.reset()
    fixtures.reset_flaky()


async def test_twenty_case_resolution_rate(run_conversation):
    results = []  # (id, type, passed, reason, prereq_ok)

    for sc in SCENARIOS:
        _reset_between_scenarios()
        fixtures.force_transient_failures(sc.get("forced_transient", 0))

        run = await run_conversation(sc["prompts"])
        passed, reason = evaluate(sc, run)
        prereq_ok = prerequisite_respected(run)
        results.append((sc["id"], sc["type"], passed, reason, prereq_ok))

    # --- per-scenario table (visible with -s) ---
    print("\n=== 20-case scenario results ===")
    for sid, stype, passed, reason, prereq_ok in results:
        flag = "PASS" if passed else "FAIL"
        pf = "" if prereq_ok else "  [PREREQ VIOLATED]"
        detail = "" if passed else f"  <- {reason}"
        print(f"  [{flag}] {sid:<28} ({stype}){detail}{pf}")

    passed_count = sum(1 for _, _, p, _, _ in results if p)
    rate = passed_count / len(results)
    print(f"=== resolution rate: {passed_count}/{len(results)} = {rate:.0%} (target ≥ {_RESOLUTION_TARGET:.0%}) ===")

    # (b) guardrail cases must each pass individually (100% requirements).
    guardrail_failures = [
        sid for sid, stype, p, _, _ in results if stype in GUARDRAIL_TYPES and not p
    ]
    assert not guardrail_failures, f"guardrail cases failed (must be 100%): {guardrail_failures}"

    # Prerequisite gate must hold in every conversation.
    prereq_failures = [sid for sid, _, _, _, ok in results if not ok]
    assert not prereq_failures, f"prerequisite gate violated in: {prereq_failures}"

    # (a) overall first-contact resolution rate.
    assert rate >= _RESOLUTION_TARGET, (
        f"resolution rate {rate:.0%} below target {_RESOLUTION_TARGET:.0%}; "
        f"failures: {[sid for sid, _, p, _, _ in results if not p]}"
    )
