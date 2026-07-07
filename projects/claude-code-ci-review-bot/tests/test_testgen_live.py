"""Integration acceptance for test generation (FR2) — real ``claude -p`` runs.

Gated on the CLI being available; uses the cheap ``BASELINE_MODEL`` (haiku) to
cap cost — ONE model call per generate. These calls are non-deterministic, so
every assert is on outcomes (the uncovered case proposed, the covered case
skipped) via tolerant keyword matching — NEVER on the model's prose (PRD
principle 5). If a delta doesn't reproduce, the fix is to iterate the fixture /
``generate-tests.md`` wording (ground truth), not to loosen the asserts.
"""

import ast
import json
import shutil

import pytest

import config
import testgen

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("claude") is None,
        reason="claude CLI not on PATH",
    ),
]


def _cases():
    return json.loads(config.TESTGEN_GROUND_TRUTH.read_text(encoding="utf-8"))["cases"]


def _diff():
    return (config.TESTGEN_REPO / config.TESTGEN_DIFF_NAME).read_text(encoding="utf-8")


def _existing():
    return (config.TESTGEN_REPO / config.TESTGEN_EXISTING_TESTS_NAME).read_text(
        encoding="utf-8"
    )


def _generate():
    import workspace

    diff, existing = _diff(), _existing()
    with workspace.staged(config.TESTGEN_REPO, include_claude_md=True) as ws:
        return testgen.generate_tests(
            diff, existing, model=config.BASELINE_MODEL, cwd=str(ws)
        )


def test_proposes_uncovered_error_path():
    """FR2: test-gen proposes a test for the uncovered out-of-range ValueError
    branch of apply_discount."""
    suggestions = _generate()
    result = testgen.score_testgen(suggestions, _cases())
    assert "rate-out-of-range" in result.matched, (
        "the uncovered ValueError branch must be proposed (net-new)"
    )


def test_skips_already_covered_happy_path():
    """FR2 headline (PRD §5 story 6): the already-covered happy path is NOT
    re-proposed. The prompt layer should skip it; ``skip_covered`` is the
    deterministic backstop."""
    suggestions = _generate()
    new, _skipped = testgen.skip_covered(
        suggestions, testgen.existing_test_names(_existing())
    )
    result = testgen.score_testgen(new, _cases())
    assert "happy-path" not in result.matched
    assert result.unexpected == [], "no already-covered case may be re-proposed"


def test_generated_code_is_real_python():
    """Best-effort structural check: each proposed test is non-empty and parses
    as Python. If haiku emits occasionally non-parseable code, relax THIS to a
    non-empty check only — never loosen the FR2 asserts above."""
    for s in _generate():
        assert s.test_code.strip(), "generated test_code must be non-empty"
        ast.parse(s.test_code)  # raises SyntaxError if not valid Python
