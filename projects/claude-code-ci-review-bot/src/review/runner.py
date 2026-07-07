"""Headless invocation of the Claude Code CLI (TR1).

The "agent" is the ``claude`` CLI itself, driven non-interactively via ``-p``.
This module owns exactly one job: shell out with ``subprocess.run`` and capture
stdout/stderr/returncode. It never blocks on input (``-p`` is non-interactive by
construction) and enforces a hard timeout — the only realistic hang is
``subprocess.TimeoutExpired``, which callers must handle as a clean failure.
"""

import subprocess
from dataclasses import dataclass


@dataclass
class RunResult:
    """Raw result of one ``claude -p`` invocation.

    ``stdout`` is pure JSON (the event array); the ``claude.ai connectors are
    disabled`` warning goes to ``stderr``. They are captured separately so the
    parser only ever ``json.loads`` the stdout stream.
    """

    stdout: str
    stderr: str
    returncode: int


def invoke_claude(
    prompt: str,
    schema_json: str,
    model: str,
    timeout_s: int,
) -> RunResult:
    """Run ``claude -p`` with schema-constrained JSON output.

    Args:
        prompt: The fully-composed prompt text (template + diff).
        schema_json: The findings schema serialized for ``--json-schema``.
        model: Model id to pass to ``--model``.
        timeout_s: Hard wall-clock cap; on expiry ``subprocess.TimeoutExpired``
            propagates (the no-hang backstop — the caller surfaces it as a
            pipeline failure, never a silent block).

    Returns:
        A ``RunResult`` with stdout/stderr captured separately.
    """
    proc = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
            "--model",
            model,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return RunResult(
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )
