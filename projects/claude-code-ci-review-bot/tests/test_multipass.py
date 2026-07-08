"""Offline tests for split_diff + multipass orchestration (TR6/TR7).

No live ``claude`` calls: ``multipass.runner.invoke_claude`` is monkeypatched to
return canned CLI output, so the fan-out shape, per-file prompt isolation, and
merge/dedupe are proven deterministically — the TR7 "N+1 independent calls"
evidence with zero tokens spent. Assertions are on structure only (call counts,
sub-diff routing, deduped result), never on model wording (PRD principle 5).
"""

import json
from pathlib import Path

import config
import multipass
import runner

_ROOT = Path(__file__).resolve().parents[1]
PR_DIFF = (_ROOT / "fixtures" / "sample-repo" / "pr.diff").read_text(encoding="utf-8")
SINGLE_DIFF = (_ROOT / "fixtures" / "pr-01" / "sample.diff").read_text(encoding="utf-8")

# Unique marker only the integration prompt carries (lets the fake tell an
# integration pass from a per-file pass without asserting on prose).
_INTEGRATION_MARKER = "spanning multiple files"

NONE_DEREF = {
    "location": {"file": "src/orders.py", "line": 24},
    "issue": "find_order can return None; order.total derefs None.",
    "severity": "high",
    "suggested_fix": "Guard for None.",
    "detected_pattern": "none-deref",
    "category": "correctness",
}
CROSS_FILE = {
    "location": {"file": "src/summary.py", "line": 14},
    "issue": "ingest writes user_id, summary reads userId -> KeyError.",
    "severity": "critical",
    "suggested_fix": "Align the key spelling.",
    "detected_pattern": "cross-file-key-mismatch",
    "category": "correctness",
}


def _canned(findings_dicts):
    """A minimal valid CLI event array wrapping ``findings_dicts``."""
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "terminal_reason": "completed",
            "structured_output": {"findings": findings_dicts},
        },
    ]
    return runner.RunResult(stdout=json.dumps(events), stderr="", returncode=0)


def _make_fake(calls):
    """Fake invoke_claude: integration prompt → cross-file; orders sub-diff →
    none-deref; every other file in isolation → clean. Records each prompt."""

    def fake_invoke(prompt, schema_json, model, timeout_s, cwd=None):
        calls.append(prompt)
        if _INTEGRATION_MARKER in prompt:  # the whole-diff integration pass
            return _canned([CROSS_FILE])
        if "src/orders.py" in prompt:  # the orders.py per-file pass
            return _canned([NONE_DEREF])
        return _canned([])  # settings / ingest / summary alone look clean

    return fake_invoke


# --- split_diff (pure) -------------------------------------------------------


def test_split_diff_four_files():
    fds = multipass.split_diff(PR_DIFF)
    assert [f.path for f in fds] == [
        "src/orders.py",
        "src/settings.py",
        "src/ingest.py",
        "src/summary.py",
    ]
    # each chunk carries its own hunk header
    assert all("@@" in f.text for f in fds)
    # round-trip: every path appears in the concatenated chunk texts
    joined = "".join(f.text for f in fds)
    for p in ("orders", "settings", "ingest", "summary"):
        assert p in joined


def test_split_diff_single_file():
    fds = multipass.split_diff(SINGLE_DIFF)
    assert len(fds) == 1
    assert fds[0].path == "src/notify.py"


def test_split_diff_empty():
    assert multipass.split_diff("") == []
    assert multipass.split_diff("   \n\n") == []


def test_split_diff_isolation():
    """A per-file chunk contains ONLY its own file — the isolation basis (TR6)."""
    fds = {f.path: f.text for f in multipass.split_diff(PR_DIFF)}
    assert "src/summary.py" not in fds["src/orders.py"]
    assert "src/orders.py" not in fds["src/summary.py"]


# --- orchestration via monkeypatch (TR7 proof) -------------------------------


def test_per_file_makes_one_call_per_file_and_isolates(monkeypatch):
    calls = []
    monkeypatch.setattr(multipass.runner, "invoke_claude", _make_fake(calls))
    findings = multipass.review_per_file(PR_DIFF, config.ENRICHED_PROMPT, "haiku")
    # exactly one independent call per file
    assert len(calls) == 4
    # each call saw ONLY its own sub-diff (isolation → can't see cross-file)
    orders_call = next(c for c in calls if "src/orders.py" in c)
    assert "src/summary.py" not in orders_call
    assert _INTEGRATION_MARKER not in orders_call
    # per-file catches the same-file none-deref, NOT the cross-file bug
    patterns = {f.detected_pattern for f in findings}
    assert "none-deref" in patterns
    assert "cross-file-key-mismatch" not in patterns


def test_integration_makes_one_call_over_whole_diff(monkeypatch):
    calls = []
    monkeypatch.setattr(multipass.runner, "invoke_claude", _make_fake(calls))
    findings = multipass.review_integration(PR_DIFF, config.INTEGRATION_PROMPT, "haiku")
    assert len(calls) == 1
    # the single call saw the whole diff (all four files present)
    for p in ("src/orders.py", "src/settings.py", "src/ingest.py", "src/summary.py"):
        assert p in calls[0]
    assert {f.detected_pattern for f in findings} == {"cross-file-key-mismatch"}


def test_multipass_makes_n_plus_one_calls_and_merges(monkeypatch):
    calls = []
    monkeypatch.setattr(multipass.runner, "invoke_claude", _make_fake(calls))
    findings = multipass.review_multipass(PR_DIFF, model="haiku")
    # N per-file (4) + 1 integration = 5 independent invoke_claude calls (TR7)
    assert len(calls) == 5
    patterns = [f.detected_pattern for f in findings]
    # both issues present, each exactly once (no contradictory/duplicate findings)
    assert patterns.count("none-deref") == 1
    assert patterns.count("cross-file-key-mismatch") == 1
    # critical sorts before high
    assert findings[0].detected_pattern == "cross-file-key-mismatch"


def test_multipass_canonical_severity_no_contradiction(monkeypatch):
    """A per-file and integration report of one pattern collapse to a single
    finding at the canonical severity — no contradictory labels (TR5)."""
    calls = []

    def fake(prompt, schema_json, model, timeout_s, cwd=None):
        calls.append(prompt)
        if _INTEGRATION_MARKER in prompt:
            # integration emits none-deref at a WRONG low severity + cross-file
            low = dict(NONE_DEREF, severity="low")
            return _canned([low, CROSS_FILE])
        if "src/orders.py" in prompt:
            return _canned([NONE_DEREF])  # per-file emits it at high
        return _canned([])

    monkeypatch.setattr(multipass.runner, "invoke_claude", fake)
    findings = multipass.review_multipass(PR_DIFF, model="haiku")
    nd = [f for f in findings if f.detected_pattern == "none-deref"]
    assert len(nd) == 1  # the low/high duplicate collapsed to one
    assert nd[0].severity == "high"  # canonical wins regardless of model label


def test_one_error_pass_does_not_sink_the_run(monkeypatch):
    """An is_error envelope from one pass yields [] for that pass; others stand."""
    def fake(prompt, schema_json, model, timeout_s, cwd=None):
        if "src/orders.py" in prompt and _INTEGRATION_MARKER not in prompt:
            events = [
                {"type": "result", "is_error": True, "terminal_reason": "error"},
            ]
            return runner.RunResult(stdout=json.dumps(events), stderr="", returncode=0)
        if _INTEGRATION_MARKER in prompt:
            return _canned([CROSS_FILE])
        return _canned([])

    monkeypatch.setattr(multipass.runner, "invoke_claude", fake)
    findings = multipass.review_multipass(PR_DIFF, model="haiku")
    # orders pass errored (no none-deref), but the integration finding survives
    patterns = {f.detected_pattern for f in findings}
    assert "cross-file-key-mismatch" in patterns
    assert "none-deref" not in patterns
