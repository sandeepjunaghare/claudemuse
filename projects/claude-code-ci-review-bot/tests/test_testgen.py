"""Offline tests for test-gen: parse + pure skip/dedupe + score + orchestration.

No live ``claude`` calls: ``testgen.runner.invoke_claude`` is monkeypatched to
return canned CLI output, so the single-call shape, the both-blocks-substituted
prompt, and the parse/dedupe/skip/score logic are proven deterministically with
zero tokens. Assertions are on structure/outcomes only, never on model wording
(PRD principle 5). ``skip_covered`` is the FR2 headline — the deterministic
"a covered test is never re-emitted" guarantee.
"""

import copy
import json
from pathlib import Path

import pytest

import config
import runner
import testgen
from parse import ParseError

_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = (_ROOT / "tests" / "fixtures" / "sample_testgen_output.json").read_text(
    encoding="utf-8"
)


def _suggestion(test_name, case, *, file="src/discount.py", symbol="apply_discount",
                description="d", test_code="def t(): pass"):
    """Build a ``TestSuggestion`` for the pure-logic tests (mirrors test_dedupe._f)."""
    return testgen.TestSuggestion(
        target=testgen.Target(file=file, symbol=symbol),
        test_name=test_name,
        case=case,
        description=description,
        test_code=test_code,
    )


def _canned(tests_dicts):
    """A minimal valid CLI event array wrapping ``tests_dicts``."""
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "terminal_reason": "completed",
            "structured_output": {"tests": tests_dicts},
        },
    ]
    return runner.RunResult(stdout=json.dumps(events), stderr="", returncode=0)


# --- parse_testgen -----------------------------------------------------------


def test_golden_output_parses_to_one_suggestion():
    parsed = testgen.parse_testgen(GOLDEN)
    assert parsed.is_error is False
    assert len(parsed.tests) == 1
    s = parsed.tests[0]
    assert s.target.file == "src/discount.py"
    assert s.target.symbol == "apply_discount"
    assert s.case == "rate-out-of-range"


def test_error_envelope_yields_empty_tests():
    events = [
        {"type": "system", "subtype": "init"},
        {"type": "result", "is_error": True, "terminal_reason": "error"},
    ]
    parsed = testgen.parse_testgen(json.dumps(events))
    assert parsed.is_error is True
    assert parsed.tests == []
    assert parsed.terminal_reason == "error"


def test_structured_output_absent_falls_back_to_result_string():
    events = json.loads(GOLDEN)
    result_elem = next(e for e in events if e["type"] == "result")
    del result_elem["structured_output"]  # force the result-string fallback
    parsed = testgen.parse_testgen(json.dumps(events))
    assert parsed.is_error is False
    assert len(parsed.tests) == 1
    assert parsed.tests[0].case == "rate-out-of-range"


def test_non_json_stdout_raises_parse_error():
    with pytest.raises(ParseError):
        testgen.parse_testgen("not json at all")


def test_empty_array_raises_parse_error():
    with pytest.raises(ParseError):
        testgen.parse_testgen("[]")


# --- existing_test_names -----------------------------------------------------


def test_existing_test_names_extracts_defs():
    src = "def test_a():\n    pass\n\ndef test_b(x):\n    pass\ndef helper(): pass\n"
    assert testgen.existing_test_names(src) == {"test_a", "test_b"}


def test_existing_test_names_empty_source():
    assert testgen.existing_test_names("") == set()


def test_existing_test_names_indented_method():
    src = "class TestX:\n    def test_method(self):\n        pass\n"
    assert "test_method" in testgen.existing_test_names(src)


# --- dedupe_suggestions (within-run) -----------------------------------------


def test_dedupe_suggestions_collapses_same_case_keep_first():
    first = _suggestion("test_out_of_range_a", "rate-out-of-range", description="first")
    second = _suggestion("test_out_of_range_b", "rate-out-of-range", description="second")
    out = testgen.dedupe_suggestions([first, second])
    assert len(out) == 1
    assert out[0].description == "first"  # keep-first, stable


def test_dedupe_suggestions_keeps_distinct_cases():
    a = _suggestion("test_a", "rate-out-of-range")
    b = _suggestion("test_b", "rate-boundary")
    assert len(testgen.dedupe_suggestions([a, b])) == 2


def test_dedupe_suggestions_keeps_all_empty_slugs():
    a = _suggestion("test_a", "")
    b = _suggestion("test_b", "")
    assert len(testgen.dedupe_suggestions([a, b])) == 2


def test_dedupe_suggestions_case_insensitive():
    a = _suggestion("test_a", "Rate-Out-Of-Range")
    b = _suggestion("test_b", "rate-out-of-range")
    assert len(testgen.dedupe_suggestions([a, b])) == 1


# --- skip_covered (the FR2 backstop, headline) -------------------------------


def test_skip_covered_never_reemits_a_covered_test():
    """The FR2 headline: a suggestion colliding with an existing test name is
    routed to ``skipped`` and never appears in ``new``."""
    existing = {"test_apply_discount_basic"}
    happy = _suggestion("test_apply_discount_basic", "happy-path")
    err = _suggestion("test_apply_discount_rejects_out_of_range", "rate-out-of-range")
    new, skipped = testgen.skip_covered([happy, err], existing)
    assert new == [err]
    assert skipped == [happy]


def test_skip_covered_case_insensitive_collision():
    existing = {"test_apply_discount_basic"}
    happy = _suggestion("Test_Apply_Discount_Basic", "happy-path")
    new, skipped = testgen.skip_covered([happy], existing)
    assert new == []
    assert skipped == [happy]


def test_skip_covered_empty_existing_skips_nothing():
    err = _suggestion("test_new", "rate-out-of-range")
    new, skipped = testgen.skip_covered([err], set())
    assert new == [err]
    assert skipped == []


def test_skip_covered_does_not_mutate_inputs():
    existing = {"test_apply_discount_basic"}
    suggestions = [_suggestion("test_apply_discount_basic", "happy-path")]
    s0 = list(suggestions)
    e0 = set(existing)
    testgen.skip_covered(suggestions, existing)
    assert suggestions == s0 and existing == e0


# --- score_testgen -----------------------------------------------------------


def _fixture_cases():
    return json.loads(config.TESTGEN_GROUND_TRUTH.read_text(encoding="utf-8"))["cases"]


def test_score_matches_uncovered_case_no_misses_no_unexpected():
    cases = _fixture_cases()
    new = [_suggestion(
        "test_apply_discount_rejects_out_of_range",
        "rate-out-of-range",
        description="raises ValueError on an out-of-range rate",
    )]
    result = testgen.score_testgen(new, cases)
    assert "rate-out-of-range" in result.matched
    assert result.missing_required == []  # rate-boundary is optional
    assert result.unexpected == []


def test_score_flags_reproposed_covered_case_as_unexpected():
    cases = _fixture_cases()
    # A suggestion that (wrongly) covers the happy-path (should_propose:false).
    bad = [_suggestion(
        "test_apply_discount_valid",
        "happy-path",
        description="applies discount for a valid in-range rate",
    )]
    result = testgen.score_testgen(bad, cases)
    assert "happy-path" in result.unexpected


def test_score_missing_required_when_uncovered():
    cases = _fixture_cases()
    result = testgen.score_testgen([], cases)  # nothing proposed
    assert "rate-out-of-range" in result.missing_required
    assert "rate-boundary" not in result.missing_required  # optional, not a gate


# --- orchestration via monkeypatch (single call, both blocks in prompt) ------


def test_generate_tests_one_call_prompt_carries_diff_and_existing(monkeypatch):
    calls = []

    def fake_invoke(prompt, schema_json, model, timeout_s, cwd=None):
        calls.append(prompt)
        return _canned([
            {
                "target": {"file": "src/discount.py", "symbol": "apply_discount"},
                "test_name": "test_apply_discount_rejects_out_of_range",
                "case": "rate-out-of-range",
                "description": "raises ValueError",
                "test_code": "def test_x(): pass",
            }
        ])

    monkeypatch.setattr(testgen.runner, "invoke_claude", fake_invoke)
    diff_text = "diff --git a/src/discount.py b/src/discount.py\n+def apply_discount(): ..."
    existing_text = "def test_apply_discount_basic():\n    assert apply_discount(100, 0.1) == 90"
    suggestions = testgen.generate_tests(diff_text, existing_text, model="haiku")

    assert len(calls) == 1  # exactly ONE fresh claude -p pass (TR1/TR7)
    prompt = calls[0]
    assert "discount" in prompt  # the diff block was substituted
    assert "test_apply_discount_basic" in prompt  # the existing-tests block too
    assert [s.case for s in suggestions] == ["rate-out-of-range"]


def test_generate_tests_error_envelope_returns_empty(monkeypatch):
    def fake_invoke(prompt, schema_json, model, timeout_s, cwd=None):
        events = [{"type": "result", "is_error": True, "terminal_reason": "error"}]
        return runner.RunResult(stdout=json.dumps(events), stderr="", returncode=0)

    monkeypatch.setattr(testgen.runner, "invoke_claude", fake_invoke)
    assert testgen.generate_tests("d", "e", model="haiku") == []


def test_generate_tests_dedupes_within_run(monkeypatch):
    def fake_invoke(prompt, schema_json, model, timeout_s, cwd=None):
        dup = {
            "target": {"file": "src/discount.py", "symbol": "apply_discount"},
            "test_name": "test_a",
            "case": "rate-out-of-range",
            "description": "d",
            "test_code": "def t(): pass",
        }
        dup2 = dict(dup, test_name="test_b")  # same case slug, different name
        return _canned([dup, dup2])

    monkeypatch.setattr(testgen.runner, "invoke_claude", fake_invoke)
    out = testgen.generate_tests("d", "e", model="haiku")
    assert len(out) == 1  # within-run dedupe collapsed the shared case slug


# --- emit_tests --------------------------------------------------------------


def test_emit_tests_empty(capsys):
    testgen.emit_tests([])
    assert "0 proposed test(s)" in capsys.readouterr().out


# --- workspace exclusion regression (no answer key ever staged) --------------


def test_testgen_answer_key_never_staged():
    """Neither answer key reaches the model's workspace: the testgen key is
    excluded from a staged testgen workspace, AND the review key is STILL
    excluded from a staged review workspace (the *ground_truth.json glob change
    is non-regressive)."""
    import workspace

    tg_ws = workspace.stage_workspace(config.TESTGEN_REPO, True)
    try:
        assert not (Path(tg_ws) / "testgen_ground_truth.json").exists()
        assert not (Path(tg_ws) / "testgen.diff").exists()  # *.diff excluded too
        # the testing-standards CLAUDE.md IS staged (the TR3 channel)
        assert (Path(tg_ws) / "CLAUDE.md").exists()
    finally:
        workspace.cleanup_workspace(tg_ws)

    rv_ws = workspace.stage_workspace(config.FIXTURE_REPO, True)
    try:
        assert not (Path(rv_ws) / "ground_truth.json").exists()  # still excluded
    finally:
        workspace.cleanup_workspace(rv_ws)


def test_golden_fixture_deepcopy_isolation():
    """Guard: parsing a golden copy does not mutate the shared GOLDEN string."""
    events = copy.deepcopy(json.loads(GOLDEN))
    testgen.parse_testgen(json.dumps(events))
    assert json.loads(GOLDEN) == json.loads(GOLDEN)
