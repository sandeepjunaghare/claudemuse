"""Test generation: propose net-new tests for a change, skip covered cases (FR2).

Two clearly separated layers, mirroring the pure/live split of ``metrics.py`` /
``multipass.py``:

* **Pure core** (``parse_testgen``, ``existing_test_names``,
  ``dedupe_suggestions``, ``skip_covered``, ``score_testgen`` + the dataclasses):
  stdlib + ``testgen_schema`` only, deterministic, never raises (except
  ``parse_testgen`` on genuinely unparseable CLI stdout, matching
  ``parse.parse_result``), no CLI/network. Unit-tested offline with no
  credentials.
* **Live driver** (``generate_tests``, ``format_test``/``emit_tests``,
  ``run_testgen_demo``): shells out to ``claude -p`` (via ``runner``) inside a
  staged workspace. Needs the CLI + a key; exercised by the integration test and
  the ``make test-gen`` target.

**The FR2 skip is two-layer, mirroring the Phase-3a dedupe design:**

1. **Prompt-context (semantic) layer** — the existing test bodies are fed into
   the prompt (``{existing_tests}``) and the model is told to propose only
   uncovered behaviors. This catches a covered case *even when the model would
   name its test differently*. (The primary mechanism.)
2. **Structural backstop (here, offline-testable)** — ``dedupe_suggestions``
   collapses suggestions sharing a ``case`` slug (within-run) and
   ``skip_covered`` drops any suggestion whose ``test_name`` collides with an
   existing test. This is the deterministic FR2 guarantee: *a covered test is
   never re-emitted*.

Honest limitation (mirrors the Phase-3a cross-end dedupe note): the structural
backstop keys on ``test_name`` collision, so a covered case re-proposed under a
*different* name is caught only by the prompt layer, not the structural key. The
offline tests prove the deterministic backstop; the live test proves the
semantic layer on the real model.

Identity for dedupe/skip is the controlled ``case`` slug (within-run) and the
``test_name`` collision (vs existing) — NEVER the ``description``/``test_code``
prose, which the model rewords every run.
"""

import json
import re
from dataclasses import dataclass

import config  # noqa: F401  (used by the live driver below; safe at import)
import runner  # noqa: F401  (used by the live driver below; safe at import)
import testgen_schema

# Reuse the single generic CLI-parse error type rather than adding a second one
# ("CLI stdout cannot be parsed" is generic enough) — one error type across the
# review + test-gen parsers.
from parse import ParseError

# --- pure core (offline) -----------------------------------------------------


@dataclass
class Target:
    """The changed function/method a proposed test covers."""

    file: str
    symbol: str


@dataclass
class TestSuggestion:
    """One proposed net-new test — the machine-parseable unit of FR2 output."""

    target: Target
    test_name: str
    case: str
    description: str
    test_code: str


@dataclass
class ParsedTestGen:
    """Outcome of parsing one test-gen ``claude -p`` run."""

    tests: list
    is_error: bool
    terminal_reason: "str | None"
    raw: list


def parse_testgen(stdout: str) -> ParsedTestGen:
    """Parse CLI stdout into a ``ParsedTestGen``.

    Mirrors ``parse.parse_result`` verbatim in shape (the ~15-line event-locating
    logic is copied, not shared — the established house pattern, e.g.
    ``dedupe._same_file`` copied from ``metrics._same_file``), but builds
    ``TestSuggestion`` objects and validates against ``TESTGEN_SCHEMA``.

    Args:
        stdout: raw stdout from ``claude -p --output-format json`` — a JSON array
            of event objects.

    Returns:
        A ``ParsedTestGen``. On a CLI ``is_error`` envelope, returns an empty
        ``tests`` list with ``is_error=True`` and the terminal reason surfaced.

    Raises:
        ParseError: if stdout is not JSON, not a non-empty list, or contains no
            ``result`` element / no parseable payload.
    """
    try:
        events = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ParseError(f"stdout is not valid JSON: {exc}\n---\n{stdout!r}") from exc

    if not isinstance(events, list) or not events:
        raise ParseError(f"expected a non-empty JSON array, got: {stdout!r}")

    result_elem = next((e for e in events if e.get("type") == "result"), None)
    if result_elem is None:
        raise ParseError(f"no element with type=='result' in event stream: {stdout!r}")

    terminal_reason = result_elem.get("terminal_reason")

    if result_elem.get("is_error"):
        return ParsedTestGen(
            tests=[],
            is_error=True,
            terminal_reason=terminal_reason,
            raw=events,
        )

    payload = result_elem.get("structured_output")
    if payload is None:
        # Fallback: the same data is available as a JSON string under "result".
        raw_result = result_elem.get("result")
        try:
            payload = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ParseError(
                f"result element has neither structured_output nor parseable "
                f"result string: {result_elem!r}"
            ) from exc

    # Belt-and-suspenders: validate even though --json-schema constrained output.
    testgen_schema.validate_tests_obj(payload)

    tests = [
        TestSuggestion(
            target=Target(
                file=t["target"]["file"],
                symbol=t["target"]["symbol"],
            ),
            test_name=t["test_name"],
            case=t["case"],
            description=t["description"],
            test_code=t["test_code"],
        )
        for t in payload["tests"]
    ]

    return ParsedTestGen(
        tests=tests,
        is_error=False,
        terminal_reason=terminal_reason,
        raw=events,
    )


def _same_file(a: str, b: str) -> bool:
    """Suffix-tolerant path match (copied verbatim from ``metrics._same_file``).

    The model may report ``discount.py`` for ``src/discount.py`` (staged-relative
    vs ground-truth-relative). Replicated here so ``testgen`` stays self-contained
    and pure — not worth a shared util module for one 3-liner (same house pattern
    as ``dedupe._same_file``).
    """
    a = (a or "").replace("\\", "/").lstrip("./")
    b = (b or "").replace("\\", "/").lstrip("./")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def existing_test_names(source: str) -> "set[str]":
    """Extract pytest test-function names (``def test_…``) from a test file.

    Handles indented methods and decorators gracefully via ``^\\s*def test_…``
    with ``re.MULTILINE``. Pure, never raises — empty/malformed source → an empty
    set. This is the coverage key for the ``skip_covered`` structural backstop.
    """
    return set(re.findall(r"^\s*def (test_\w+)\s*\(", source or "", re.MULTILINE))


def dedupe_suggestions(suggestions: "list[TestSuggestion]") -> "list[TestSuggestion]":
    """Collapse within-run suggestions sharing a ``case`` slug, keeping FIRST.

    Identity is the normalized ``case`` slug (``strip().lower()``). Empty-slug
    suggestions are all kept — you can't dedupe an unnamed case (mirrors
    ``dedupe.is_duplicate``'s empty-pattern fallback rationale). Stable, pure,
    returns a new list, never mutates the input.
    """
    seen: "set[str]" = set()
    kept: "list[TestSuggestion]" = []
    for s in suggestions:
        slug = (s.case or "").strip().lower()
        if slug and slug in seen:
            continue
        if slug:
            seen.add(slug)
        kept.append(s)
    return kept


def skip_covered(
    suggestions: "list[TestSuggestion]",
    existing_names: "set[str]",
) -> "tuple[list[TestSuggestion], list[TestSuggestion]]":
    """Split ``suggestions`` into ``(new, skipped)`` by test-name collision.

    Mirrors ``dedupe.suppress_prior``'s ``(new, still)`` shape. A suggestion is
    ``skipped`` if its ``test_name`` (normalized ``strip().lower()``) is already
    in ``existing_names`` (normalized the same way); otherwise it is ``new``.

    This is the deterministic structural backstop — the FR2 "never re-emit a
    covered test" guarantee. Pure, never raises, never mutates inputs.
    """
    existing_norm = {n.strip().lower() for n in existing_names}
    new: "list[TestSuggestion]" = []
    skipped: "list[TestSuggestion]" = []
    for s in suggestions:
        if (s.test_name or "").strip().lower() in existing_norm:
            skipped.append(s)
        else:
            new.append(s)
    return new, skipped


@dataclass
class TestGenResult:
    """Outcome of scoring proposed tests against the test-gen ground truth."""

    proposed: list  # case ids (ground-truth) covered by some suggestion
    skipped_covered: list  # placeholder for driver-supplied skipped case ids
    matched: list  # should_propose:true case ids covered by some suggestion
    missing_required: list  # should_propose:true non-optional case ids NOT covered
    unexpected: list  # should_propose:false case ids that WERE covered (FR2 failure)


def _covers(s: TestSuggestion, case: dict) -> bool:
    """True if suggestion ``s`` covers ground-truth ``case`` by keyword presence.

    The model GENERATES the ``case`` slug + ``description`` (nondeterministic
    wording), so coverage is a tolerant keyword match over
    ``case + description + test_name`` — a structural-ish signal, never an
    assertion on exact prose (PRD principle 5).
    """
    hay = f"{s.case} {s.description} {s.test_name}".lower()
    return any(kw.lower() in hay for kw in case.get("keywords", []))


def score_testgen(
    suggestions: "list[TestSuggestion]",
    cases: "list[dict]",
) -> TestGenResult:
    """Score ``suggestions`` against test-gen ground-truth ``cases``. Pure.

    * ``matched`` — ids of ``should_propose:true`` cases covered by a suggestion.
    * ``missing_required`` — ids of ``should_propose:true`` NON-optional cases not
      covered (the hard-gate misses).
    * ``unexpected`` — ids of ``should_propose:false`` cases that WERE covered
      (a covered case re-proposed — the FR2 failure). Recorded, never raised.
    * ``proposed`` — all case ids (any ``should_propose``) covered by a suggestion.
    """
    proposed = [c["id"] for c in cases if any(_covers(s, c) for s in suggestions)]

    positive = [c for c in cases if c.get("should_propose")]
    negative = [c for c in cases if not c.get("should_propose")]

    matched = [
        c["id"] for c in positive if any(_covers(s, c) for s in suggestions)
    ]
    missing_required = [
        c["id"]
        for c in positive
        if not c.get("optional") and c["id"] not in matched
    ]
    unexpected = [
        c["id"] for c in negative if any(_covers(s, c) for s in suggestions)
    ]

    return TestGenResult(
        proposed=proposed,
        skipped_covered=[],
        matched=matched,
        missing_required=missing_required,
        unexpected=unexpected,
    )


# --- live driver + emit (integration: needs CLI + key) -----------------------


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


def generate_tests(
    diff_text: str,
    existing_tests_text: str,
    *,
    prompt_path=None,
    model: str,
    cwd: "str | None" = None,
) -> "list[TestSuggestion]":
    """Run ONE headless ``claude -p`` test-gen pass and return its suggestions.

    Composes the versioned prompt (substituting BOTH ``{diff}`` and
    ``{existing_tests}`` via ``str.replace`` — diffs and code contain ``{``/``}``,
    so ``str.format`` is wrong), runs a single fresh ``invoke_claude`` call
    (TR1/TR7), parses (TR2), and applies the within-run ``dedupe_suggestions``
    layer. Tolerant of an error envelope (``is_error`` → ``[]``) so one bad run
    does not crash the pipeline. The ``skip_covered`` structural backstop runs in
    the CALLER (the demo/CLI), mirroring how ``cli.py`` applies
    ``dedupe.suppress_prior`` around ``multipass.review_multipass`` — so each
    layer is exercisable independently.
    """
    prompt_path = prompt_path if prompt_path is not None else config.TESTGEN_PROMPT
    template = _load_template(prompt_path)
    prompt = template.replace("{diff}", diff_text).replace(
        "{existing_tests}", existing_tests_text
    )
    result = runner.invoke_claude(
        prompt,
        testgen_schema.as_json_string(),
        model,
        config.CLAUDE_TIMEOUT_S,
        cwd=cwd,
    )
    parsed = parse_testgen(result.stdout)
    if parsed.is_error:
        return []
    return dedupe_suggestions(parsed.tests)


def format_test(t: TestSuggestion) -> str:
    """Format one proposed test as a header line + its indented ``test_code``.

    Mirrors ``post.format_comment``: a legible ``file::test_name [case] desc``
    header, then the generated test source indented under it.
    """
    indented = "\n".join("    " + ln for ln in t.test_code.splitlines())
    return (
        f"{t.target.file}::{t.test_name} [{t.case}] {t.description}\n"
        f"{indented}"
    )


def emit_tests(tests: "list[TestSuggestion]") -> None:
    """Print a count header followed by one formatted block per proposed test."""
    print(f"{len(tests)} proposed test(s)")
    for t in tests:
        print(format_test(t))


def run_testgen_demo() -> dict:
    """``make test-gen`` (LIVE): generate net-new tests for the fixture change.

    Reads the fixture diff + existing tests, stages the ``testgen-sample`` repo
    once (so the run auto-loads its testing-standards ``CLAUDE.md`` — TR3), runs
    ONE ``claude -p`` pass, applies the ``skip_covered`` structural backstop,
    scores against the answer key, emits the net-new tests, prints the headline,
    and writes ``data/metrics/testgen.json``. Returns a summary dict.
    """
    import json as _json

    import workspace

    diff = (config.TESTGEN_REPO / config.TESTGEN_DIFF_NAME).read_text(encoding="utf-8")
    existing = (config.TESTGEN_REPO / config.TESTGEN_EXISTING_TESTS_NAME).read_text(
        encoding="utf-8"
    )

    with workspace.staged(config.TESTGEN_REPO, include_claude_md=True) as ws:
        suggestions = generate_tests(
            diff, existing, model=config.BASELINE_MODEL, cwd=str(ws)
        )

    existing_names = existing_test_names(existing)
    new, skipped = skip_covered(suggestions, existing_names)

    cases = _json.loads(config.TESTGEN_GROUND_TRUTH.read_text(encoding="utf-8"))["cases"]
    result = score_testgen(new, cases)

    emit_tests(new)
    uncovered_proposed = "rate-out-of-range" in result.matched
    print(
        f"\nproposed net-new: {len(new)}"
        f"\nskipped (already covered): {len(skipped)}"
        f"\ncovered case re-proposed (should be 0): {len(result.unexpected)}"
        f"\nuncovered error-path proposed: {uncovered_proposed}"
    )

    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposed_net_new": len(new),
        "skipped_already_covered": len(skipped),
        "covered_reproposed": result.unexpected,
        "matched": result.matched,
        "missing_required": result.missing_required,
        "uncovered_error_path_proposed": uncovered_proposed,
    }
    (config.METRICS_DIR / "testgen.json").write_text(
        _json.dumps(payload, indent=2), encoding="utf-8"
    )
    return {
        "new": new,
        "skipped": skipped,
        "result": result,
        "uncovered_error_path_proposed": uncovered_proposed,
    }
