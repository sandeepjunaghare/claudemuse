"""Precision/recall scorer + live review driver (TR4/TR5).

Two clearly separated layers:

* **Pure scorer** (``MetricsResult``, ``match``, ``score``, ``format_report``):
  stdlib-only, deterministic, never raises, no CLI/network. It is unit-tested
  offline and is the *ground-truth check on the ground-truth harness* — a wrong
  scorer would make the headline trust metric a lie.
* **Live driver** (``run_variant``, ``run_metrics``, ``run_tr3_demo``): shells
  out to ``claude -p`` (via ``runner``) inside a staged workspace and scores the
  result. These need the CLI + a key and are exercised by the integration tests
  and the ``make metrics`` / ``make tr3-demo`` targets.

Scoring rules (single-pass, Phase 2):
  * Cases with ``requires_integration_pass=true`` are EXCLUDED from single-pass
    recall (the cross-file bug the design can't yet catch) and reported
    separately as a known gap — keeping the P2 number honest.
  * A ``should_flag=true`` eligible case is a TP if any finding matches it, else
    an FN.
  * A finding is an FP if it matches a ``should_flag=false`` case, or matches no
    eligible case at all (spurious).
"""

import json
from dataclasses import dataclass

from parse import Finding

# --- pure scorer (offline) ---------------------------------------------------


@dataclass
class MetricsResult:
    """Outcome of scoring one review against the ground-truth cases."""

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    matched: list  # case ids correctly flagged
    false_positives: list  # (file, line, issue) tuples for spurious/should-not findings
    missed: list  # case ids that should have been flagged but weren't
    known_gaps: list  # case ids excluded from single-pass recall (integration-only)
    known_gap_hits: list  # gap case ids the single pass DID catch (bonus, not scored)


def _same_file(finding_file: str, case_file: str) -> bool:
    """Suffix-tolerant path match — the model may report ``orders.py`` for
    ``src/orders.py`` (staged relative vs ground-truth relative)."""
    a = (finding_file or "").replace("\\", "/").lstrip("./")
    b = (case_file or "").replace("\\", "/").lstrip("./")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def match(finding: Finding, case: dict, tolerance: int) -> bool:
    """True if ``finding`` locates ``case`` (same file, line within tolerance).

    A case may pin a single ``file``/``line`` OR list several acceptable
    ``locations`` (e.g. a cross-file bug reportable at either the producer or the
    consumer end) — a finding matching any listed location counts.
    """
    locations = case.get("locations")
    if not locations:
        locations = [{"file": case.get("file", ""), "line": case.get("line")}]
    for loc in locations:
        if not _same_file(finding.location.file, loc.get("file", "")):
            continue
        loc_line = loc.get("line")
        if loc_line is None or abs(finding.location.line - loc_line) <= tolerance:
            return True
    return False


def score(
    findings: "list[Finding]",
    cases: "list[dict]",
    *,
    tolerance: int,
    single_pass: bool = True,
) -> MetricsResult:
    """Score ``findings`` against ground-truth ``cases``. Pure, never raises."""
    gap_cases = [
        c
        for c in cases
        if single_pass and c.get("requires_integration_pass")
    ]
    eligible = [c for c in cases if c not in gap_cases]
    known_gaps = [c["id"] for c in gap_cases]

    positive_cases = [c for c in eligible if c.get("should_flag")]
    negative_cases = [c for c in eligible if not c.get("should_flag")]

    matched, missed = [], []
    for case in positive_cases:
        if any(match(f, case, tolerance) for f in findings):
            matched.append(case["id"])
        else:
            missed.append(case["id"])

    known_gap_hits, false_positives = [], []
    for f in findings:
        # A finding is legitimate if it matches a should_flag=true eligible case.
        if any(match(f, c, tolerance) for c in positive_cases):
            continue
        # A finding matching a known-gap case (integration-only) is a BONUS in
        # single-pass mode — not counted against precision (the design doesn't
        # yet require catching it), just recorded.
        gap = next((c for c in gap_cases if match(f, c, tolerance)), None)
        if gap is not None:
            known_gap_hits.append(gap["id"])
            continue
        # Otherwise it is an FP — a should_flag=false case or a spurious finding.
        false_positives.append((f.location.file, f.location.line, f.issue))

    tp = len(matched)
    fn = len(missed)
    fp = len(false_positives)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    # Suppress the unused var warning about negative_cases while keeping the
    # explicit split readable — negatives influence FP via the match check above.
    _ = negative_cases

    return MetricsResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        matched=matched,
        false_positives=false_positives,
        missed=missed,
        known_gaps=known_gaps,
        known_gap_hits=known_gap_hits,
    )


def format_report(baseline: MetricsResult, enriched: MetricsResult) -> str:
    """A before/after table string (the headline trust metric)."""
    lines = [
        "Precision/Recall — before (baseline prompt) vs after (enriched TR4/TR5)",
        "",
        f"{'metric':<12}{'baseline':>12}{'enriched':>12}",
        f"{'-' * 36}",
        f"{'precision':<12}{baseline.precision:>12.3f}{enriched.precision:>12.3f}",
        f"{'recall':<12}{baseline.recall:>12.3f}{enriched.recall:>12.3f}",
        f"{'f1':<12}{baseline.f1:>12.3f}{enriched.f1:>12.3f}",
        f"{'tp/fp/fn':<12}"
        f"{f'{baseline.tp}/{baseline.fp}/{baseline.fn}':>12}"
        f"{f'{enriched.tp}/{enriched.fp}/{enriched.fn}':>12}",
    ]
    if enriched.known_gaps:
        lines.append("")
        lines.append(
            f"known single-pass gaps (excluded from recall): "
            f"{', '.join(enriched.known_gaps)}"
        )
        hits = enriched.known_gap_hits or baseline.known_gap_hits
        if hits:
            lines.append(
                f"  (single pass opportunistically caught: {', '.join(sorted(set(hits)))})"
            )
    return "\n".join(lines)


# --- live driver (integration: needs CLI + key) ------------------------------


def _strip_frontmatter(text: str) -> str:
    """Remove a leading ``---`` YAML frontmatter block (mirrors cli._strip)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return text


def run_variant(
    prompt_path,
    model: str,
    *,
    include_claude_md: bool = True,
    diff_name: str = "pr.diff",
) -> "list[Finding]":
    """Run one live review variant and return canonical-severity findings.

    Reads+strips the prompt, substitutes the fixture diff, stages a clean
    workspace (with/without the fixture ``CLAUDE.md``), runs ``claude -p`` with
    ``cwd`` = the staged dir, parses, and applies canonical severity.
    """
    import config
    import parse
    import runner
    import schema
    import severity
    import workspace
    from pathlib import Path

    template = _strip_frontmatter(Path(prompt_path).read_text(encoding="utf-8"))
    diff_text = (config.FIXTURE_REPO / diff_name).read_text(encoding="utf-8")
    prompt = template.replace("{diff}", diff_text)

    with workspace.staged(config.FIXTURE_REPO, include_claude_md=include_claude_md) as ws:
        result = runner.invoke_claude(
            prompt,
            schema.as_json_string(),
            model,
            config.CLAUDE_TIMEOUT_S,
            cwd=str(ws),
        )
    review = parse.parse_result(result.stdout)
    return severity.apply_canonical_severity(review.findings)


def _load_cases() -> "list[dict]":
    import config

    data = json.loads(config.GROUND_TRUTH.read_text(encoding="utf-8"))
    return data["cases"]


def _write_metrics(name: str, result: MetricsResult) -> None:
    import config

    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "tp": result.tp,
        "fp": result.fp,
        "fn": result.fn,
        "precision": result.precision,
        "recall": result.recall,
        "f1": result.f1,
        "matched": result.matched,
        "missed": result.missed,
        "false_positives": result.false_positives,
        "known_gaps": result.known_gaps,
        "known_gap_hits": result.known_gap_hits,
    }
    (config.METRICS_DIR / f"{name}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def run_metrics() -> dict:
    """``make metrics``: baseline vs enriched, both with CLAUDE.md present.

    Scores each, writes ``data/metrics/{baseline,enriched}.json``, prints the
    before/after table, and returns both results.
    """
    import config

    cases = _load_cases()
    baseline_findings = run_variant(config.BASELINE_PROMPT, config.BASELINE_MODEL)
    enriched_findings = run_variant(config.ENRICHED_PROMPT, config.BASELINE_MODEL)

    baseline = score(
        baseline_findings, cases, tolerance=config.LINE_MATCH_TOLERANCE
    )
    enriched = score(
        enriched_findings, cases, tolerance=config.LINE_MATCH_TOLERANCE
    )

    _write_metrics("baseline", baseline)
    _write_metrics("enriched", enriched)

    print(format_report(baseline, enriched))
    return {"baseline": baseline, "enriched": enriched}


def run_tr3_demo() -> dict:
    """``make tr3-demo``: prompt held constant, CLAUDE.md present vs absent.

    Reports whether the convention-dependent case (the ``should_flag=false``
    single-pass case — correct only under the fixture CLAUDE.md policy) was
    flagged in each arm. Expected: absent → flagged (a false positive that only
    the project convention exonerates), present → not flagged.

    Uses the BASELINE prompt as the constant. This isolates CLAUDE.md as the only
    variable AND keeps the signal observable: the enriched prompt is deliberately
    conservative ("when in doubt, don't flag"), so it suppresses the borderline
    finding on its own — leaving nothing for CLAUDE.md to change. The baseline
    prompt readily surfaces the borderline finding, so CLAUDE.md's suppression
    (the TR3 mechanism) becomes measurable.
    """
    import config

    cases = _load_cases()
    pct_case = next(
        c
        for c in cases
        if not c.get("should_flag") and not c.get("requires_integration_pass")
    )

    present = run_variant(
        config.BASELINE_PROMPT, config.BASELINE_MODEL, include_claude_md=True
    )
    absent = run_variant(
        config.BASELINE_PROMPT, config.BASELINE_MODEL, include_claude_md=False
    )

    def flagged(findings):
        return any(
            match(f, pct_case, config.LINE_MATCH_TOLERANCE) for f in findings
        )

    present_flagged = flagged(present)
    absent_flagged = flagged(absent)

    _write_tr3(pct_case["id"], present_flagged, absent_flagged)

    print(f"TR3 present-vs-absent behavior change ({pct_case['id']} case):")
    print(f"  CLAUDE.md PRESENT -> flagged: {present_flagged}  (expected False)")
    print(f"  CLAUDE.md ABSENT  -> flagged: {absent_flagged}  (expected True)")
    changed = present_flagged != absent_flagged
    print(f"  behavior changed: {changed}")
    return {"present_flagged": present_flagged, "absent_flagged": absent_flagged}


def _write_tr3(case_id: str, present_flagged: bool, absent_flagged: bool) -> None:
    import config

    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    (config.METRICS_DIR / "tr3-demo.json").write_text(
        json.dumps(
            {
                "case": case_id,
                "claude_md_present_flagged": present_flagged,
                "claude_md_absent_flagged": absent_flagged,
                "behavior_changed": present_flagged != absent_flagged,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
