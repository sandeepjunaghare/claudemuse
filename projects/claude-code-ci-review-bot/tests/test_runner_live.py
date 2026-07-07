"""Integration test: real ``claude -p`` on the fixture PR (TR1/TR2).

Gated on the CLI being present; uses the cheap haiku tier to cap cost
(~$0.03/run). Asserts on structure/exit/no-hang only — never on model wording,
which is non-deterministic.
"""

import shutil
import subprocess

import pytest

import parse
import runner
import schema

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("claude") is None, reason="claude CLI not on PATH"
    ),
]

_PROMPT = (
    "Review this diff. Report genuine issues only via the structured output. "
    "location.line is the new-file line number.\n\n"
    "diff --git a/src/notify.py b/src/notify.py\n"
    "--- a/src/notify.py\n"
    "+++ b/src/notify.py\n"
    "@@ -1,3 +1,6 @@\n"
    "+def find(users, name):\n"
    "+    match = [u for u in users if u.name == name]\n"
    "+    if match == None:\n"
    "+        return None\n"
)


def test_live_review_completes_and_parses():
    result = runner.invoke_claude(
        _PROMPT,
        schema.as_json_string(),
        model="claude-haiku-4-5-20251001",
        timeout_s=120,
    )
    # No hang: if invoke_claude returned, TimeoutExpired did not fire.
    assert result.returncode == 0
    assert result.stdout.strip()

    review = parse.parse_result(result.stdout)
    assert review.is_error is False
    # Every finding is schema-valid (parse re-validates) and maps to a location.
    for f in review.findings:
        assert isinstance(f.location.file, str) and f.location.file
        assert isinstance(f.location.line, int)


def test_invoke_does_not_hang():
    # Explicitly assert no TimeoutExpired propagates within a generous cap.
    try:
        runner.invoke_claude(
            _PROMPT,
            schema.as_json_string(),
            model="claude-haiku-4-5-20251001",
            timeout_s=120,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("claude -p hung past the timeout (TR1 violation)")
