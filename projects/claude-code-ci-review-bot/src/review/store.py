"""Persist / load prior findings per PR for duplicate suppression (TR8/FR3).

The filesystem half of the dedupe design: ``dedupe.py`` is pure and stateless,
so the "what did we report last run?" memory lives here. Findings are stored as
JSON under ``config.PRIOR_FINDINGS_DIR/{pr_id}.json`` and round-tripped
loss-free through the ``Finding`` dataclass.

Mirrors ``metrics._write_metrics`` / ``_load_cases`` for the read/write + mkdir
idiom. The ``base_dir`` override lets tests point at a tmp dir so the repo store
is never polluted. A missing store (first run) yields ``[]`` — never raises.
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

import config
from parse import Finding, Location


def _pr_id(diff_path: str) -> str:
    """Derive a stable PR id from a diff path.

    The filename stem with any non-alphanumeric chars collapsed to ``-`` (e.g.
    ``fixtures/sample-repo/pr.diff`` → ``pr``). Used when ``--pr-id`` isn't
    given explicitly.
    """
    stem = Path(diff_path).stem
    slug = re.sub(r"[^0-9A-Za-z]+", "-", stem).strip("-")
    return slug or "pr"


def finding_to_dict(f: Finding) -> dict:
    """Serialize a ``Finding`` to a plain dict.

    ``dataclasses.asdict`` recurses into the nested ``Location``, giving
    ``{"location": {"file":…, "line":…}, "issue":…, ...}``.
    """
    return asdict(f)


def finding_from_dict(d: dict) -> Finding:
    """Rebuild a ``Finding`` from a dict produced by ``finding_to_dict``."""
    return Finding(
        location=Location(d["location"]["file"], d["location"]["line"]),
        issue=d["issue"],
        severity=d["severity"],
        suggested_fix=d["suggested_fix"],
        detected_pattern=d["detected_pattern"],
        category=d["category"],
    )


def save_findings(
    pr_id: str,
    findings: "list[Finding]",
    *,
    base_dir: "Path | None" = None,
) -> Path:
    """Write ``findings`` to ``{base_dir or PRIOR_FINDINGS_DIR}/{pr_id}.json``.

    Creates the directory if absent. Returns the written path. ``base_dir``
    defaults to ``config.PRIOR_FINDINGS_DIR`` (production); tests pass a tmp dir.
    """
    directory = Path(base_dir) if base_dir is not None else config.PRIOR_FINDINGS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{pr_id}.json"
    payload = {"pr_id": pr_id, "findings": [finding_to_dict(f) for f in findings]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_prior(
    pr_id: str,
    *,
    base_dir: "Path | None" = None,
) -> "list[Finding]":
    """Load prior findings for ``pr_id``; a missing store → ``[]`` (never raises).

    The first run of any PR has no prior file, so an absent store is the normal
    "nothing reported yet" case, not an error.
    """
    directory = Path(base_dir) if base_dir is not None else config.PRIOR_FINDINGS_DIR
    path = directory / f"{pr_id}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [finding_from_dict(d) for d in data.get("findings", [])]
