"""Multi-pass review orchestration: per-file passes + integration pass (TR6/TR7).

Two layers, mirroring the pure/live split of ``metrics.py``:

* **Pure core** (``split_diff``): splits a unified diff into per-file sub-diffs.
  Stdlib-only, deterministic, never raises, unit-tests offline.
* **Live driver** (``review_per_file`` / ``review_integration`` /
  ``review_multipass`` + demo runners): each fans out ``claude -p`` calls via
  ``runner.invoke_claude``, parses, canonicalizes severity, and dedupes.

**TR6 (multi-pass):** the diff is split per file; each file is reviewed in its
own pass (focused attention, no dilution on a large PR); a *separate* integration
pass reviews the WHOLE diff for cross-module / data-flow defects that per-file
isolation provably cannot see (the seeded ``cross-file-key-mismatch``).

**TR7 (independent instance):** every pass is its own ``claude -p`` subprocess
with zero shared reasoning context — N per-file + 1 integration = N+1 fully
independent ``invoke_claude`` calls. This is a structural property (a process
boundary), never ``--continue``/``--resume`` and never feeding one pass's output
into another's prompt. It is proven offline in ``test_multipass.py`` by counting
the calls under a monkeypatched ``invoke_claude``.
"""

from dataclasses import dataclass

import config
import dedupe
import parse
import runner
import schema
import severity


# --- pure core (offline) -----------------------------------------------------


@dataclass
class FileDiff:
    """One file's self-contained sub-diff, carved out of a unified diff."""

    path: str
    text: str


def _split_on_prefix(lines: "list[str]", prefix: str) -> "list[str]":
    """Group ``lines`` into chunks, each starting at a line beginning ``prefix``.

    The prefix line is kept with the chunk it opens. If no line matches, the
    whole input is returned as a single chunk.
    """
    chunks: "list[str]" = []
    current: "list[str]" = []
    for ln in lines:
        if ln.startswith(prefix) and current:
            chunks.append("".join(current))
            current = [ln]
        else:
            current.append(ln)
    if current:
        chunks.append("".join(current))
    return chunks


def _strip_ab(path: str) -> str:
    """Strip a leading ``a/`` or ``b/`` git prefix from a diff path."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _derive_path(chunk: str) -> str:
    """Derive the file path for a sub-diff chunk.

    Prefer the ``+++ b/<path>`` line (the new file); if that is ``/dev/null``
    (a deletion), use the ``--- a/<path>`` line; else fall back to the
    ``diff --git a/… b/…`` b-path.
    """
    plus = minus = gitline = None
    for ln in chunk.splitlines():
        if ln.startswith("+++ ") and plus is None:
            plus = ln[4:].strip()
        elif ln.startswith("--- ") and minus is None:
            minus = ln[4:].strip()
        elif ln.startswith("diff --git ") and gitline is None:
            gitline = ln
    if plus and plus != "/dev/null":
        return _strip_ab(plus)
    if minus and minus != "/dev/null":
        return _strip_ab(minus)
    if gitline:
        parts = gitline.split()
        if len(parts) >= 4:
            return _strip_ab(parts[3])
    return ""


def split_diff(diff_text: str) -> "list[FileDiff]":
    """Split a unified diff into per-file ``FileDiff`` chunks (TR6 foundation).

    Splits on ``diff --git `` boundaries when present (each starts a new file);
    otherwise falls back to ``--- `` boundaries for a bare ``---/+++`` diff; a
    diff with neither marker is returned as one chunk. Each chunk keeps its
    leading ``diff --git``/``---``/``+++``/``@@`` headers verbatim so the
    per-file prompt gets valid diff structure and correct new-file line numbers
    (hunks are NOT renumbered). Empty / whitespace-only input → ``[]``.
    """
    if not diff_text or not diff_text.strip():
        return []
    lines = diff_text.splitlines(keepends=True)
    if any(ln.startswith("diff --git ") for ln in lines):
        chunks = _split_on_prefix(lines, "diff --git ")
    else:
        chunks = _split_on_prefix(lines, "--- ")
    return [FileDiff(path=_derive_path(c), text=c) for c in chunks]


# --- live driver (integration: needs CLI + key) ------------------------------


def _strip_frontmatter(text: str) -> str:
    """Remove a leading ``---`` YAML frontmatter block (mirrors cli._strip)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return text


def _load_template(prompt_path) -> str:
    """Read + frontmatter-strip a versioned prompt file."""
    from pathlib import Path

    return _strip_frontmatter(Path(prompt_path).read_text(encoding="utf-8"))


def _run_pass(
    prompt_template: str,
    diff_text: str,
    model: str,
    cwd: "str | None",
) -> "list[Finding]":
    """Run ONE independent ``claude -p`` pass and return its findings.

    A fresh ``invoke_claude`` call = a fresh process with no shared context
    (TR7). Tolerant of an error/empty review (``is_error`` → ``[]``) so one bad
    pass does not sink the whole multipass run. Uses ``str.replace`` (not
    ``str.format``) because diffs contain ``{`` / ``}``.
    """
    prompt = prompt_template.replace("{diff}", diff_text)
    result = runner.invoke_claude(
        prompt,
        schema.as_json_string(),
        model,
        config.CLAUDE_TIMEOUT_S,
        cwd=cwd,
    )
    review = parse.parse_result(result.stdout)
    return [] if review.is_error else review.findings


def review_per_file(
    diff_text: str,
    prompt_path,
    model: str,
    *,
    cwd: "str | None" = None,
) -> "list[Finding]":
    """Review each file in the diff in its OWN isolated pass (TR6/TR7).

    ``split_diff`` carves the diff per file; each file gets a separate
    ``claude -p`` call seeing ONLY its own sub-diff — so a per-file pass provably
    cannot connect a producer/consumer key mismatch across files. Findings are
    concatenated and within-run deduped. (Sequential is fine and deterministic
    for the fixture; the passes are independent and could be parallelized.)
    """
    template = _load_template(prompt_path)
    all_findings: "list[Finding]" = []
    for fd in split_diff(diff_text):
        all_findings.extend(_run_pass(template, fd.text, model, cwd))
    return dedupe.dedupe(all_findings, tolerance=config.DEDUPE_LINE_TOLERANCE)


def review_integration(
    diff_text: str,
    integration_prompt_path,
    model: str,
    *,
    cwd: "str | None" = None,
) -> "list[Finding]":
    """Run the single cross-file integration pass over the WHOLE diff (TR6/TR7).

    One fresh ``claude -p`` instance sees all files at once — the only pass that
    can catch cross-module / data-flow / contract defects.
    """
    template = _load_template(integration_prompt_path)
    return _run_pass(template, diff_text, model, cwd)


def review_multipass(
    diff_text: str,
    *,
    prompt_path=None,
    integration_prompt_path=None,
    model: str,
    cwd: "str | None" = None,
) -> "list[Finding]":
    """Full multipass review: N per-file passes + 1 integration pass (TR6/TR7).

    The integration findings are placed FIRST so its cross-file finding wins
    keep-first on any overlap. ``apply_canonical_severity`` runs BEFORE dedupe so
    a per-file and an integration report of the same pattern carry identical
    severity and collapse cleanly → "no contradictory findings" is structurally
    true. Returns the merged, deduped, severity-sorted findings.
    """
    prompt_path = prompt_path if prompt_path is not None else config.ENRICHED_PROMPT
    integration_prompt_path = (
        integration_prompt_path
        if integration_prompt_path is not None
        else config.INTEGRATION_PROMPT
    )
    per_file = review_per_file(diff_text, prompt_path, model, cwd=cwd)
    integ = review_integration(diff_text, integration_prompt_path, model, cwd=cwd)
    merged = integ + per_file  # integration first (keep-first wins on overlap)
    canonical = severity.apply_canonical_severity(merged)
    deduped = dedupe.dedupe(canonical, tolerance=config.DEDUPE_LINE_TOLERANCE)
    return severity.sort_by_severity(deduped)


# --- demo drivers (make review-multi / dedupe-demo; LIVE, multi-pass) --------


def run_multipass_demo() -> dict:
    """``make review-multi``: multipass on the fixture ``pr.diff``, scored.

    Stages the fixture (CLAUDE.md present) once, runs ``review_multipass`` with
    ``cwd`` = the staged dir, scores against the answer key with
    ``single_pass=False`` (so the cross-file case is now an eligible positive),
    prints the findings + whether the integration pass caught the cross-file
    bug, and writes ``data/metrics/multipass.json``.
    """
    import json

    import metrics
    import post
    import workspace

    cases = json.loads(config.GROUND_TRUTH.read_text(encoding="utf-8"))["cases"]
    diff_text = (config.FIXTURE_REPO / "pr.diff").read_text(encoding="utf-8")

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        findings = review_multipass(diff_text, model=config.BASELINE_MODEL, cwd=str(ws))

    result = metrics.score(
        findings, cases, tolerance=config.LINE_MATCH_TOLERANCE, single_pass=False
    )
    caught_cross_file = "cross-file-key-mismatch" in result.matched

    post.emit(findings)
    print(
        f"\ncross-file bug caught by integration pass: {caught_cross_file}"
        f"\nnone-deref caught: {'none-deref' in result.matched}"
        f"\nsettings-broad-except (should NOT flag) flagged: "
        f"{'settings-broad-except' in [c[0] for c in result.false_positives] or bool(result.false_positives)}"
        f"\nprecision={result.precision:.3f} recall={result.recall:.3f} "
        f"tp/fp/fn={result.tp}/{result.fp}/{result.fn}"
    )

    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    (config.METRICS_DIR / "multipass.json").write_text(
        json.dumps(
            {
                "cross_file_caught_by_integration": caught_cross_file,
                "matched": result.matched,
                "false_positives": result.false_positives,
                "precision": result.precision,
                "recall": result.recall,
                "tp": result.tp,
                "fp": result.fp,
                "fn": result.fn,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"findings": findings, "cross_file_caught": caught_cross_file, "result": result}


def run_dedupe_demo() -> dict:
    """``make dedupe-demo``: multipass twice on ``pr.diff``; zero dupes on re-run.

    Runs ``review_multipass`` once (saved as the prior), runs it again, then
    ``suppress_prior`` against the saved prior — the second-run NEW comments
    should be ~0 (all issues already reported).
    """
    import store
    import workspace

    diff_text = (config.FIXTURE_REPO / "pr.diff").read_text(encoding="utf-8")

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        first = review_multipass(diff_text, model=config.BASELINE_MODEL, cwd=str(ws))
    store.save_findings("demo", first)

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=True) as ws:
        second = review_multipass(diff_text, model=config.BASELINE_MODEL, cwd=str(ws))

    new, still = dedupe.suppress_prior(
        second, store.load_prior("demo"), tolerance=config.DEDUPE_LINE_TOLERANCE
    )
    print(
        f"first-run findings: {len(first)}"
        f"\nsecond-run findings: {len(second)}"
        f"\nsecond-run NEW comments (should be ~0): {len(new)}"
        f"\nstill-unresolved suppressed: {len(still)}"
        f"\nduplicate comments on re-run: {len(new)}"
    )
    return {"first": first, "second": second, "new": new, "still": still}
