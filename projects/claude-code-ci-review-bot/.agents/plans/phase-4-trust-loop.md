# Feature: Phase 4 — Trust Loop (TR9 / FR4 + `gh --post` + semantic dedupe)

The following plan should be complete, but it is important that you validate documentation and
codebase patterns and task sanity before you start implementing. Pay special attention to naming of
existing utils, types, and models. Import from the right files (flat absolute imports — `import
config`, `from parse import Finding, Location` — because `src/review` is on `sys.path` via
`tests/conftest.py`).

## Feature Description

Phase 4 closes the loop that makes the reviewer *trustworthy and controllable*. It adds four things,
all offline-first (pure functions unit-tested with no `claude -p` and no network):

1. **False-positive instrumentation + category quarantine (TR9/FR4).** A new `instrument.py` tracks
   dismissed findings *by `detected_pattern`* in a JSON store, computes a *per-category* dismissal
   rate, and quarantines (filters out) a category whose rate crosses a threshold — plus a manual
   override list. Quarantining one category must leave every other category emitting normally.
2. **Real `gh` PR posting behind `--post` (FR1, PRD Risk #6).** A **pure, unit-tested** `gh`
   command-argv builder + a guarded shell-out that only runs when a real PR is supplied. Default
   stays **emit** (print). `--post` without `--pr` errors; `--post --dry-run` prints the exact `gh`
   argv without executing.
3. **Prompt-context (semantic) dedupe layer (TR8 completion).** Feed prior findings *into the review
   prompt* so the model itself reports only new/still-unresolved issues — completing the two-layer
   dedupe design (the structural backstop already exists) and resolving the cross-end duplicate drift
   the Phase-3a review documented (`make dedupe-demo` currently prints "duplicate comments on
   re-run: 1").

## User Story

As a **bot owner (the wary team lead)**
I want to **quarantine a high-false-positive category, post findings to a real PR when I choose to,
and never see duplicate comments across re-runs**
So that **I can silence a noisy category without losing the good ones, keep review threads readable,
and trust the bot enough to wire it into a real pipeline.**

## Problem Statement

The bot currently emits findings and suppresses *structural* duplicates, but:
- It has **no feedback loop**: there is no way to record that a finding was dismissed, no way to
  measure which patterns/categories are noisy, and no lever to disable a bad category (TR9/FR4 are
  unbuilt — `instrument.py` does not exist, though `detected_pattern`/`category` are already on every
  `Finding`).
- It **cannot post to GitHub**: `post.emit` only prints; nothing imports `gh` (Phase-4 deferral).
- Its dedupe is **one layer only**: `cli.py` loads prior findings and calls `dedupe.suppress_prior`
  (structural), but never feeds them into the prompt. The `dedupe.py` docstring claims a
  prompt-context layer exists "elsewhere — cli.py"; **that wiring was never built** (aspirational).
  The consequence is the documented cross-end drift: the cross-file bug is reportable at either the
  producer (`ingest.py`) or consumer (`summary.py`) end, the model picks a different end on re-run,
  and the structural key (file + pattern + line) correctly treats two files as distinct → 1 duplicate.

## Solution Statement

- **`instrument.py`** — mirror the pure-core + file-store split used by `severity.py`/`dedupe.py`
  (pure) and `store.py` (file I/O). Pure functions over a store dict: `record_dismissal`,
  `record_emitted`, `category_dismissal_rates`, `auto_quarantined` (rate threshold + min-sample
  guard), `quarantined_categories` (auto ∪ manual), `apply_quarantine` → `(kept, dropped)`. File I/O:
  `load_store`/`save_store` (missing → default; `base_dir` override for tests, exactly like
  `store.py`). A committed **seed** store drives a deterministic **offline** `make quarantine-demo`;
  the runtime store lives at `data/dismissed_patterns.json` (gitignored).
- **`gh --post`** — add pure `format_review_body` + `build_gh_comment_args` to `post.py` (argv only,
  no shell), plus a guarded `post_via_gh(..., dry_run)` that shells out only when not a dry run. Wire
  `--post`/`--pr`/`--repo`/`--dry-run` into `cli.py`. Unit tests assert the argv shape and that
  `dry_run=True` never calls the injected runner; the real shell-out is integration-gated and
  skip-by-default (no live PR in the MVP).
- **Semantic dedupe** — add a `{prior_findings}` block to the *enriched* review prompt and the
  integration prompt (NOT the baseline prompt — it must stay a frozen metrics artifact). Add a pure
  `render_prior_findings(prior)` (empty → a neutral sentinel so first-run behavior is unchanged).
  `cli.py` and `multipass.py` inject the rendered prior text into the prompt; the structural
  `suppress_prior` remains the backstop; the persisted prior **accumulates** (`dedupe(prior +
  current)`) so a previously-reported issue is never forgotten.

## Feature Metadata

**Feature Type**: Enhancement (new capability layered on the Phase 1–3 spine)
**Estimated Complexity**: Medium-High (four sub-features; three touch the CLI hot path)
**Primary Systems Affected**: `src/review/` (`instrument.py` NEW, `post.py`, `cli.py`, `multipass.py`,
`dedupe.py`, `config.py`), the two review prompts, `fixtures/`, `data/`, `Makefile`, `tests/`.
**Dependencies**: No new pip deps. `gh` CLI (already required per global instructions; only touched on
the guarded real-post path). Stdlib `subprocess` (already used by `runner.py`).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — YOU MUST READ THESE BEFORE IMPLEMENTING

- `src/review/store.py` (all 89 lines) — Why: the **exact** file-I/O idiom to mirror in
  `instrument.py`: `base_dir: Path | None = None` override defaulting to a `config.*` path, `mkdir(
  parents=True, exist_ok=True)`, missing store → `[]`/default (never raises), `json.dumps(...,
  indent=2)`. `save_findings`/`load_prior` are the template for `save_store`/`load_store`.
- `src/review/dedupe.py` (all 106 lines) — Why: the pure-function idiom (`_same_file`,
  `suppress_prior` returning a `(kept, other)` tuple) that `apply_quarantine` and `record_*` mirror;
  and where `render_prior_findings` will live. Note the module docstring already *describes* the
  prompt-context layer — update it to say it is now implemented in `cli.py`/`multipass.py`.
- `src/review/cli.py` (all 201 lines) — Why: the hot path you extend. Note `_compose_prompt` (line
  42, `str.replace` not `str.format`), the `--pr-id` dedupe block (lines 182-193, where the semantic
  layer + accumulation land), the `contextlib.ExitStack`/`workspace.staged` cwd handling (lines
  119-142), and `post.emit(findings)` at line 195 (where the quarantine filter + `--post` branch go).
- `src/review/multipass.py` (all 318 lines) — Why: `_run_pass` (line 136, `prompt.replace("{diff}",
  ...)`), `review_per_file`/`review_integration`/`review_multipass` signatures to thread
  `prior_findings=` through, and `run_dedupe_demo` (line 288) to update so the second run receives the
  first run's findings as prior (the cross-end-drift fix + validation).
- `src/review/post.py` (all 30 lines) — Why: `format_comment` (line 12) is reused by
  `format_review_body`; `emit` (line 25) stays the default. All new `gh` code goes here.
- `src/review/config.py` (all 123 lines) — Why: the `#:`-doc-commented constant idiom and the exact
  `PROJECT_ROOT`/`parents[4]` path anchors. New constants for the store paths + thresholds go in the
  Phase-4 section you append.
- `src/review/severity.py` (lines 88-119) — Why: `canonical_severity` + `apply_canonical_severity`
  show the pure-transform idiom (`dataclasses.replace`, never mutate); `apply_quarantine` follows the
  same no-mutation contract.
- `src/review/parse.py` (lines 24-52) — Why: the `Finding`/`Location` dataclass field order
  (`location, issue, severity, suggested_fix, detected_pattern, category`) — every hand-authored
  `Finding` in tests/fixtures must match it exactly.
- `.claude/commands/review/review-diff.md` (all 92 lines) — Why: the enriched prompt you add a
  `{prior_findings}` block to (just before the `Unified diff to review:` block at line 88).
- `.claude/commands/review/review-integration.md` (all 79 lines) — Why: same `{prior_findings}` block
  addition (before line 74).
- `tests/conftest.py` (all 65 lines) — Why: the `sys.path`/`claude_runnable()` gate and the
  `sample_findings` fixture shape; reuse `claude_runnable` to gate any integration test.
- `tests/test_store.py`, `tests/test_dedupe.py` — Why: the exact offline test idiom
  (`base_dir=tmp_path`, `_f(...)` finding factory, no-mutation assertions) for `test_instrument.py`.
- `tests/test_cli.py` (all 64 lines) — Why: the `monkeypatch.setattr(runner, "invoke_claude", ...)` +
  `capsys` + `cli.main([...])` idiom for the new CLI tests (prompt-carries-prior, quarantine-applied,
  `--post --dry-run`).
- `tests/test_multipass.py` (all 194 lines) — Why: the `_make_fake(calls)` prompt-capture idiom —
  reuse it to assert the composed prompt now contains a prior finding's slug when `prior_findings` is
  threaded in.

### New Files to Create

- `src/review/instrument.py` — TR9/FR4 pure core (dismissal tracking, rate, quarantine) + store I/O.
- `fixtures/dismissed_patterns.seed.json` — committed seed store driving the deterministic offline
  quarantine demo (one noisy category over threshold, one clean category, a min-sample entry that must
  NOT trip). This is the demo input; the runtime store at `data/dismissed_patterns.json` is separate
  and gitignored.
- `tests/test_instrument.py` — offline unit tests for the whole `instrument.py` surface.

### Files to Update

- `src/review/config.py` — Phase-4 constants (store paths + thresholds).
- `src/review/post.py` — `format_review_body`, `build_gh_comment_args`, `post_via_gh`.
- `src/review/dedupe.py` — `render_prior_findings` + docstring correction.
- `src/review/cli.py` — semantic-layer injection, prior accumulation, quarantine filter, `--post`/
  `--pr`/`--repo`/`--dry-run` flags and branch.
- `src/review/multipass.py` — thread `prior_findings=` through the passes; update `run_dedupe_demo`;
  add `run_quarantine_demo` (offline).
- `.claude/commands/review/review-diff.md`, `.claude/commands/review/review-integration.md` — add the
  `{prior_findings}` block.
- `.gitignore` — add `data/dismissed_patterns.json`.
- `Makefile` — `quarantine-demo` (offline) + `post-dry-run` (offline) targets; update `.PHONY`.
- `tests/test_post.py`, `tests/test_dedupe.py`, `tests/test_cli.py` — extend with the new assertions.
- `_tasks/todo.md` — Phase-4 checklist + review section (house style).

### Relevant Documentation — READ BEFORE IMPLEMENTING

- Claude Code headless / structured output: https://code.claude.com/docs/en/headless
  - Why: confirm `-p`/`--output-format json`/`--json-schema` semantics are unchanged (Phase-4 does not
    alter the invocation; it only changes prompt composition and post-processing).
- `gh pr comment` manual: https://cli.github.com/manual/gh_pr_comment
  - Section: `--body`, `--repo`, positional `{<number> | <url> | <branch>}`.
  - Why: the argv builder targets `gh pr comment <pr> --body <body> [--repo <repo>]` as the robust,
    just-needs-a-PR path. (True line-anchored *review* comments need a commit SHA via `gh api
    repos/{owner}/{repo}/pulls/{n}/comments` — NOT derivable from a bare diff file; documented as a
    noted extension, not built in the MVP. The finding body carries `file:line` so location is
    preserved in the posted text.)
- `gh api` manual: https://cli.github.com/manual/gh_api — Why: reference for the noted inline-comment
  extension only.

### Patterns to Follow

**Pure core + file-store split (mirror `dedupe.py` + `store.py`):**
```python
# instrument.py — pure, never raises, no CLI/network in the core functions
def apply_quarantine(findings, quarantined):
    kept, dropped = [], []
    for f in findings:
        (dropped if (f.category or "").strip() in quarantined else kept).append(f)
    return kept, dropped   # mirrors dedupe.suppress_prior's (new, still) shape
```

**File store with `base_dir` override (verbatim idiom from `store.py:55-89`):**
```python
def load_store(*, base_dir=None):
    path = (Path(base_dir) if base_dir is not None else config.DISMISSED_PATTERNS_STORE.parent) \
        / config.DISMISSED_PATTERNS_STORE.name
    if not path.exists():
        return {"patterns": {}, "manual_quarantine": []}   # default, never raises
    return json.loads(path.read_text(encoding="utf-8"))
```

**Prompt composition (`str.replace`, never `str.format` — diffs contain `{`/`}`), from `cli.py:42`
and `multipass.py:149`:**
```python
prompt = template.replace("{diff}", diff).replace("{prior_findings}", prior_text)
```

**No-mutation pure transforms (`dataclasses.replace`), from `severity.py:101-107`** — `record_*`
returns a NEW store dict (deep-copy the mutated sub-dicts); never mutate the argument.

**Config constant doc-comments (`#:`), from `config.py`:**
```python
#: Runtime dismissal store (written by `instrument --dismiss`; gitignored like the other data/ files).
DISMISSED_PATTERNS_STORE = PROJECT_ROOT / "data" / "dismissed_patterns.json"
```

**Guarded outward action with injectable runner (so unit tests never shell out):**
```python
def post_via_gh(findings, pr, *, repo=None, dry_run=False, run=subprocess.run):
    args = build_gh_comment_args(pr, format_review_body(findings), repo=repo)
    if dry_run:
        print("DRY RUN — would run: " + " ".join(args)); return 0
    return run(args, check=False).returncode
```

**Anti-patterns to avoid:**
- Do NOT import `anthropic`, `claude-agent-sdk`, or the Messages API anywhere (grep must stay clean).
- Do NOT add `import` of `gh` as a library — `gh` is a CLI reached via `subprocess` only, on the
  guarded path.
- Do NOT modify the **baseline** prompt (`review-diff.baseline.md`) — it is the frozen "before"
  metrics arm; adding `{prior_findings}` there would contaminate the A/B.
- Do NOT match dedupe/quarantine on `issue` prose (nondeterministic); key on `detected_pattern` /
  `category` slugs.
- Do NOT let the default review path (no `--pr-id`, no populated store) change by a single byte — the
  quarantine filter over an absent store must be a no-op, and the `{prior_findings}` sentinel on first
  run must not alter model behavior meaningfully. Preserve the Phase-1/2/3 "defaults byte-for-byte"
  discipline.

---

## IMPLEMENTATION PLAN

### Phase 4.1: Foundation — config + store shape + seed fixture

Add Phase-4 constants to `config.py`; define the store schema; author the committed seed. This
unblocks the pure `instrument.py` core and its offline tests.

**Store schema** (`data/dismissed_patterns.json` runtime + `fixtures/dismissed_patterns.seed.json`):
```json
{
  "patterns": {
    "none-deref":        {"category": "correctness",     "emitted": 12, "dismissed": 0},
    "speculative-perf":  {"category": "performance",     "emitted": 8,  "dismissed": 6},
    "style-nit":         {"category": "maintainability", "emitted": 10, "dismissed": 7},
    "rare-guess":        {"category": "security",        "emitted": 2,  "dismissed": 2}
  },
  "manual_quarantine": []
}
```
- Category dismissal rate = Σ dismissed / Σ emitted over the patterns in that category.
- With `QUARANTINE_RATE_THRESHOLD = 0.5` and `QUARANTINE_MIN_SAMPLE = 3` (min Σ emitted per category
  to be eligible): `performance` (6/8=0.75) and `maintainability` (7/10=0.70) auto-quarantine;
  `security` (2/2=1.0) is **excluded** by the min-sample guard (only 2 emitted — proves rare noise
  does not nuke a category); `correctness` (0/12) stays clean. This gives the demo a clean,
  deterministic story: quarantine performance+maintainability, keep correctness+security emitting.

### Phase 4.2: Core — `instrument.py` (pure + store I/O)

Implement the pure functions and the file store. Fully offline-testable.

### Phase 4.3: Core — `gh --post` builder + guarded post in `post.py`

Pure argv builder + body formatter + guarded `post_via_gh`. Unit-test the pure parts and the
`dry_run` short-circuit.

### Phase 4.4: Core — semantic dedupe (`render_prior_findings` + prompt blocks)

Pure renderer in `dedupe.py`; `{prior_findings}` block in the enriched + integration prompts.

### Phase 4.5: Integration — wire into `cli.py` + `multipass.py`

Semantic-layer injection, prior accumulation, quarantine filter, `--post` branch (CLI); thread
`prior_findings` through the passes and update `run_dedupe_demo` (multipass). Add offline demos.

### Phase 4.6: Testing & Validation

Offline unit tests for every pure function + CLI edge; one focused integration test for the semantic
layer; skip-by-default integration test for the real `gh` post. Run the 5 validation levels.

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task ends with an executable validation command. Run
`make test-unit` (the offline suite) after each code task; it must stay green and grow.

### UPDATE `src/review/config.py`

- **IMPLEMENT**: Append a `# --- Phase 4: trust loop (TR9/FR4) + gh posting ---` section with:
  - `DISMISSED_PATTERNS_STORE = PROJECT_ROOT / "data" / "dismissed_patterns.json"` (runtime, gitignored)
  - `DISMISSED_PATTERNS_SEED = PROJECT_ROOT / "fixtures" / "dismissed_patterns.seed.json"` (committed demo input)
  - `QUARANTINE_RATE_THRESHOLD = 0.5`
  - `QUARANTINE_MIN_SAMPLE = 3`
  - each with a `#:` doc-comment explaining seed-vs-runtime separation and the min-sample rationale.
- **PATTERN**: `config.py:42-107` (the phased-section + `#:` idiom).
- **GOTCHA**: The PRD names `data/dismissed_patterns.json`; keep that as the **runtime** path. The
  **committed seed** deliberately lives under `fixtures/` to avoid git churn on a runtime-mutated
  file — note this deviation in the module comment and `_tasks/todo.md`.
- **VALIDATE**: `../../.venv/bin/python -c "import sys; sys.path.insert(0,'src/review'); import config; print(config.DISMISSED_PATTERNS_STORE, config.QUARANTINE_RATE_THRESHOLD)"`

### CREATE `fixtures/dismissed_patterns.seed.json`

- **IMPLEMENT**: The seed JSON from Phase 4.1 (4 patterns across 4 categories, `manual_quarantine: []`).
- **GOTCHA**: `category` values MUST be from the controlled set `correctness | security | performance
  | maintainability` (the schema/prompt vocabulary). `emitted >= dismissed` for every entry.
- **VALIDATE**: `../../.venv/bin/python -c "import json; d=json.load(open('fixtures/dismissed_patterns.seed.json')); assert set(v['category'] for v in d['patterns'].values()) <= {'correctness','security','performance','maintainability'}; print('seed ok')"`

### CREATE `src/review/instrument.py`

- **IMPLEMENT** (pure core, stdlib-only, never raises, no CLI/network — mirror `dedupe.py`'s module
  docstring style):
  - `_STORE_DEFAULT = {"patterns": {}, "manual_quarantine": []}` (return a fresh copy each call).
  - `record_emitted(store, findings) -> dict` — return a NEW store; for each finding, ensure a
    `patterns[pattern]` entry (`{"category":…, "emitted":0, "dismissed":0}`) and `emitted += 1`.
    Skip findings with an empty `detected_pattern`.
  - `record_dismissal(store, pattern, category=None) -> dict` — NEW store; ensure the entry (infer
    category from arg or leave existing), `dismissed += 1`. Never let `dismissed` exceed nothing —
    it's a raw counter.
  - `category_dismissal_rates(store) -> dict[str, float]` — aggregate Σdismissed/Σemitted per
    category; skip categories with Σemitted == 0 (avoid ZeroDivision).
  - `category_sample_sizes(store) -> dict[str, int]` — Σemitted per category (for the min-sample guard).
  - `auto_quarantined(store, *, threshold, min_sample) -> list[str]` — sorted list of categories with
    rate >= threshold AND Σemitted >= min_sample.
  - `quarantined_categories(store, *, threshold, min_sample) -> list[str]` — sorted union of
    `auto_quarantined(...)` and `store.get("manual_quarantine", [])`.
  - `apply_quarantine(findings, quarantined) -> tuple[list[Finding], list[Finding]]` — `(kept,
    dropped)`, pure, no mutation; a finding is dropped iff its `category` (stripped) is in
    `quarantined`. Empty `quarantined` → `(all, [])`.
  - Store I/O (mirror `store.py`): `load_store(*, path=None) -> dict` (missing → `_STORE_DEFAULT`
    copy; never raises); `save_store(store, *, path=None) -> Path` (`mkdir(parents=True,
    exist_ok=True)`, `json.dumps(indent=2)`). Default `path=config.DISMISSED_PATTERNS_STORE`.
    Accept a `path=` override (a full file path) for tests — simpler than `store.py`'s `base_dir`
    because there is exactly one store file, not one-per-PR.
  - Optional thin `main(argv=None)` (argparse) for the ops action: `--dismiss <pattern> [--category
    <c>]` loads the runtime store, `record_dismissal`, `save_store`, prints the new count. Keep it
    tiny and below an `if __name__ == "__main__":` guard, mirroring `cli.py:199`.
- **PATTERN**: pure core = `dedupe.py`; store I/O = `store.py:55-89`; no-mutation = `severity.py:101`.
- **IMPORTS**: `import json`, `from pathlib import Path`, `import config`, `from parse import
  Finding`. (No `dataclasses` needed unless you add a result dataclass — not required.)
- **GOTCHA**: Return NEW dicts from `record_*` — `import copy; s = copy.deepcopy(store)` then mutate
  `s`. A test asserts the input store is unchanged. Guard every division against Σemitted == 0.
- **VALIDATE**: `../../.venv/bin/python -m py_compile src/review/instrument.py`

### CREATE `tests/test_instrument.py`

- **IMPLEMENT** offline tests (mirror `test_store.py` + `test_dedupe.py`):
  - `_f(file, line, pattern, category)` finding factory (copy from `test_dedupe.py:16`, add category).
  - `load_store` missing path → default; `save_store`→`load_store` round-trip with `path=tmp_path/"s.json"`.
  - `record_emitted` / `record_dismissal` increment correctly, create entries, **do not mutate input**.
  - `category_dismissal_rates` on the seed shape → correctness 0.0, performance 0.75, maintainability
    0.70, security 1.0.
  - `auto_quarantined` with threshold=0.5, min_sample=3 → `["maintainability","performance"]`
    (security excluded by min-sample; correctness below threshold). **This is the FR4 min-sample gate.**
  - `quarantined_categories` unions the manual override (set `manual_quarantine:["security"]` in a
    constructed store → security appears even though min-sample would exclude it).
  - `apply_quarantine`: **the FR4 headline** — given findings across correctness/performance/
    maintainability/security and `quarantined=["performance","maintainability"]`, `kept` retains
    exactly the correctness + security findings and `dropped` is exactly the other two; input list
    unchanged.
  - Load the actual committed seed via `config.DISMISSED_PATTERNS_SEED` and assert
    `auto_quarantined` matches the story (regression-locks the seed).
- **PATTERN**: `tests/test_store.py` (base_dir/tmp), `tests/test_dedupe.py` (parametrize + no-mutation).
- **VALIDATE**: `make test-unit` (new tests pass; count rises from 113).

### UPDATE `src/review/post.py`

- **IMPLEMENT**:
  - `format_review_body(findings) -> str` — a markdown body: a header line (`N finding(s)`) then one
    `- ` bullet per finding reusing the `format_comment` content (so `file:line [sev] issue` +
    fix/pattern/category are all present). Empty findings → a "No findings." body.
  - `build_gh_comment_args(pr, body, *, repo=None) -> list[str]` — returns
    `["gh","pr","comment", str(pr), "--body", body]` plus `["--repo", repo]` when `repo` is truthy.
    Pure; no shell-out.
  - `post_via_gh(findings, pr, *, repo=None, dry_run=False, run=subprocess.run) -> int` — build args
    from `format_review_body`; if `dry_run` print `"DRY RUN — would run: " + " ".join(args)` and
    return 0; else `return run(args, check=False).returncode`. Injectable `run` so unit tests pass a
    fake and assert it is/ isn't called.
- **PATTERN**: `post.format_comment` (line 12) reused; guarded-runner pattern from the plan header.
- **IMPORTS**: add `import subprocess` at the top of `post.py`.
- **GOTCHA**: Keep `emit` and `format_comment` byte-for-byte (existing `test_post.py` asserts their
  output). `gh` is only ever a subprocess argv — never an import. The body must NOT be shell-escaped
  manually; pass it as a single argv element (subprocess handles it without a shell).
- **VALIDATE**: `../../.venv/bin/python -m py_compile src/review/post.py`

### UPDATE `tests/test_post.py`

- **IMPLEMENT** (append; keep existing tests untouched):
  - `test_format_review_body_contains_each_finding_location` — body has each finding's `file:line`.
  - `test_build_gh_comment_args_shape` — with and without `repo`; asserts `["gh","pr","comment",...]`
    and `--repo` presence/absence; `--body` value equals the formatted body.
  - `test_post_via_gh_dry_run_does_not_shell_out` — pass a fake `run` that raises if called; assert
    `dry_run=True` returns 0 and the fake was never invoked; capsys shows `DRY RUN`.
  - `test_post_via_gh_executes_when_not_dry_run` — fake `run` returns an object with `.returncode=0`
    and records the argv; assert it was called once with the built args and `post_via_gh` returns 0.
- **VALIDATE**: `make test-unit`

### UPDATE `src/review/dedupe.py`

- **IMPLEMENT**: `render_prior_findings(prior: list[Finding]) -> str` (pure, stdlib-only). Empty →
  the sentinel `"(none — this is the first review of this PR)"`. Non-empty → a stable, sorted
  (`by file, line`) bullet list: `- {file}:{line} [{detected_pattern}] {issue}`. This is the text the
  model reads to know what NOT to repeat.
- **UPDATE**: the module docstring's two-layer note (lines 11-17) — change "Prompt-context (elsewhere
  — cli.py / the review prompt)" from aspirational to "implemented: `cli.py`/`multipass.py` inject
  `render_prior_findings(...)` into the `{prior_findings}` prompt slot."
- **PATTERN**: pure/no-IO like the rest of `dedupe.py`.
- **GOTCHA**: Sort deterministically (never rely on input order) so the composed prompt is stable
  across runs — a wobbling prompt would make the semantic layer nondeterministic.
- **VALIDATE**: `../../.venv/bin/python -m py_compile src/review/dedupe.py`

### UPDATE `tests/test_dedupe.py`

- **IMPLEMENT** (append): `test_render_prior_findings_empty_is_sentinel` (empty → contains "first
  review"); `test_render_prior_findings_lists_each` (each prior finding's file, line, and
  `detected_pattern` slug appear; ordering is stable regardless of input order).
- **VALIDATE**: `make test-unit`

### UPDATE `.claude/commands/review/review-diff.md`

- **IMPLEMENT**: Insert, immediately before the `Unified diff to review:` block (line 88), a section:
  ```
  ## Previously reported on this PR (do NOT repeat)

  The issues below were already reported on an earlier commit of this PR. Report ONLY new or
  still-unresolved issues. Do NOT re-report an issue already listed here if it is unchanged.

  {prior_findings}
  ```
- **PATTERN**: matches the existing `{diff}` fenced-placeholder convention at line 90.
- **GOTCHA**: The composer uses `str.replace("{prior_findings}", ...)`; a template lacking the token
  is a silent no-op, so adding the token is backward-compatible for any caller that doesn't set it.
- **VALIDATE**: `grep -q "{prior_findings}" .claude/commands/review/review-diff.md && echo ok`

### UPDATE `.claude/commands/review/review-integration.md`

- **IMPLEMENT**: Same `## Previously reported` block + `{prior_findings}` placeholder, before the
  `Unified diff to review (all files):` block (line 74).
- **GOTCHA**: Do **NOT** touch `.claude/commands/review/review-diff.baseline.md` (frozen metrics arm).
- **VALIDATE**: `grep -q "{prior_findings}" .claude/commands/review/review-integration.md && echo ok`

### UPDATE `src/review/multipass.py`

- **IMPLEMENT**:
  - Thread `prior_findings: "list[Finding] | None" = None` through `review_per_file`,
    `review_integration`, and `review_multipass`. Render once
    (`prior_text = dedupe.render_prior_findings(prior_findings or [])`) and pass to `_run_pass`.
  - `_run_pass(prompt_template, diff_text, model, cwd, prior_text="")` → `prompt =
    prompt_template.replace("{diff}", diff_text).replace("{prior_findings}", prior_text)`.
  - Update `run_dedupe_demo` (line 288): pass the **first** run's findings as `prior_findings=` into
    the **second** `review_multipass`, then run the structural `suppress_prior` against the saved
    prior as today. Expect `new ≈ 0` including the cross-file end (the drift fix) and print it.
  - ADD `run_quarantine_demo() -> dict` (OFFLINE — no `claude -p`, no key): load the committed seed
    (`instrument.load_store(path=config.DISMISSED_PATTERNS_SEED)`), build a hand-authored
    multi-category `Finding` list, compute `quarantined_categories`, `apply_quarantine`, and print
    `quarantined categories`, `findings before/after`, and confirmation that correctness+security
    survive while performance+maintainability are dropped. Use local imports inside the demo driver
    (house pattern — see `run_multipass_demo`'s `import json/metrics/post/workspace`).
- **PATTERN**: `_run_pass` (line 136); demo-driver-local-imports (line 241, 297).
- **GOTCHA**: `_run_pass` currently has a positional `cwd`; add `prior_text` as a keyword with a `""`
  default so existing internal calls stay valid. Keep `review_multipass`'s
  `apply_canonical_severity`→`dedupe`→`sort` tail unchanged.
- **VALIDATE**: `../../.venv/bin/python -m py_compile src/review/multipass.py` and `make test-unit`
  (the existing `test_multipass.py` call-count tests must still pass — the fake `invoke_claude`
  ignores extra prompt content).

### UPDATE `src/review/cli.py`

- **IMPLEMENT**:
  - New args: `--post` (store_true), `--pr` (default None; the PR number/URL/branch for `gh`),
    `--repo` already exists for TR3 staging — **do not reuse it for gh**; add a distinct `--gh-repo`
    (default None) so the two concerns don't collide. `--dry-run` (store_true; with `--post`, prints
    the `gh` argv instead of executing).
  - Argument validation: if `--post` and not `--pr` → print an error to stderr and `return 1`
    (mirrors the missing-diff exit-1 idiom at line 106).
  - Update `_compose_prompt(template, diff, prior_text="")` → also `.replace("{prior_findings}",
    prior_text)`.
  - **Semantic layer + accumulation**: when `args.pr_id`, load prior BEFORE composing the prompt;
    `prior_text = dedupe.render_prior_findings(prior)`; inject into the single-mode prompt and pass
    `prior_findings=prior` to `review_multipass` in multi mode. When no `--pr-id`, `prior_text =
    dedupe.render_prior_findings([])` (sentinel) so the token still resolves.
  - In the existing `--pr-id` block (lines 182-193): after computing `new, still`, persist the
    **accumulated** prior: `store.save_findings(args.pr_id, dedupe.dedupe(prior + findings,
    tolerance=config.DEDUPE_LINE_TOLERANCE))` (never forget a previously-reported issue). Keep the
    "N still-unresolved suppressed" stderr note. `findings = new`.
  - **Quarantine filter** (both modes, right before emit/post): `q =
    instrument.quarantined_categories(instrument.load_store(),
    threshold=config.QUARANTINE_RATE_THRESHOLD, min_sample=config.QUARANTINE_MIN_SAMPLE)`; `findings,
    dropped = instrument.apply_quarantine(findings, q)`; if `dropped`, print a one-line stderr note
    (`f"({len(dropped)} finding(s) filtered by quarantined categories: {', '.join(q)})"`). Absent
    store → `q == []` → no-op (default path unchanged).
  - **Emit/post branch**: replace `post.emit(findings)` (line 195) with: if `args.post`:
    `return post.post_via_gh(findings, args.pr, repo=args.gh_repo, dry_run=args.dry_run)` (its int
    return becomes the exit code — but map a nonzero gh returncode to a clear stderr note first);
    else `post.emit(findings)` then `return 0`.
  - **IMPORTS**: add `import instrument`.
- **PATTERN**: arg-parsing + exit-1 idiom (`cli.py:56-108`); ExitStack cwd (line 119).
- **GOTCHA**: `--repo` (TR3 staging cwd) and `--gh-repo` (gh target) are DIFFERENT — do not conflate.
  The quarantine filter reads the RUNTIME store (`data/dismissed_patterns.json`), which is absent by
  default, so `make ci-review PR=fixtures/pr-01/sample.diff` must stay byte-for-byte identical (1
  finding, exit 0). Verify this in Level 5.
- **VALIDATE**: `../../.venv/bin/python -m py_compile src/review/cli.py` and `make ci-review PR=fixtures/pr-01/sample.diff < /dev/null` (still exit 0, 1 finding, no hang).

### UPDATE `tests/test_cli.py`

- **IMPLEMENT** (append; reuse the `monkeypatch.setattr(runner, "invoke_claude", ...)` + `capsys` idiom):
  - `test_prompt_carries_prior_findings_when_pr_id_given` — pre-seed a prior via
    `store.save_findings(pr_id, [finding], base_dir=...)` OR monkeypatch `store.load_prior` to return
    a known finding; capture the composed prompt by having the fake `invoke_claude` record its
    `prompt` arg; assert the prior finding's `detected_pattern` slug appears in the prompt. (Use a
    tmp store or monkeypatch to avoid touching `data/`.)
  - `test_quarantine_filters_before_emit` — monkeypatch `instrument.load_store` to return a store
    whose rates quarantine `performance`; fake `invoke_claude` returns one correctness + one
    performance finding; assert the emitted output contains the correctness finding and not the
    performance one, and the stderr note fired.
  - `test_default_path_unchanged_when_store_absent` — monkeypatch `instrument.load_store` → default
    empty; fake returns one finding; assert it is emitted (no filtering), exit 0.
  - `test_post_requires_pr` — `cli.main(["--diff", diff, "--post"])` → rc 1, stderr mentions `--pr`.
  - `test_post_dry_run_prints_gh_argv` — fake `invoke_claude` returns one finding; `cli.main(["--diff",
    diff, "--post", "--pr", "42", "--dry-run"])` → rc 0, stdout contains `DRY RUN` + `gh pr comment`.
    (Ensure no real `gh` runs — dry_run path never shells out.)
- **GOTCHA**: These tests must not write to the repo's `data/` store — monkeypatch `load_store`/
  `load_prior` or pass tmp paths. Follow `test_store.py`'s discipline.
- **VALIDATE**: `make test-unit`

### UPDATE `.gitignore`

- **IMPLEMENT**: add under the existing data-artifacts section:
  ```
  # Runtime dismissal store (mutated by `instrument --dismiss` — TR9/FR4); the committed demo input
  # is fixtures/dismissed_patterns.seed.json, not this file.
  data/dismissed_patterns.json
  ```
- **VALIDATE**: `git check-ignore data/dismissed_patterns.json && echo ignored`

### UPDATE `Makefile`

- **IMPLEMENT**:
  - `quarantine-demo:` → `PYTHONPATH=$(PYTHONPATH) $(PY) -c "import multipass; multipass.run_quarantine_demo()"`
    with a comment noting it is **OFFLINE** (no CLI/key) — pure quarantine over the seed store.
  - `post-dry-run:` → runs `ci-review` with `--post --pr <n> --dry-run` over the pr-01 fixture, so a
    user can see the `gh` argv without posting. Comment it as offline/no-post. Example recipe:
    `PYTHONPATH=$(PYTHONPATH) $(PY) -m cli --diff fixtures/pr-01/sample.diff --post --pr 1 --dry-run < /dev/null`
  - Add both to `.PHONY`.
- **PATTERN**: existing target/comment idiom (`Makefile:21-44`).
- **VALIDATE**: `make quarantine-demo` (prints the quarantine story, exit 0, no key needed) and
  `make post-dry-run` (prints `DRY RUN ... gh pr comment`, exit 0, does not post).

### CREATE `tests/test_dedupe_semantic_live.py` [integration]

- **IMPLEMENT**: one `@pytest.mark.integration` + `@pytest.mark.skipif(not claude_runnable())` test
  (mirror `test_multipass_live.py`'s re-run test) that runs `review_multipass` on `pr.diff` once,
  then again with `prior_findings=<first run>`; assert the second run's structural `suppress_prior`
  yields **0** new comments for the reliably-located `none-deref` (pin it precisely, as
  `test_multipass_live` does, to sidestep any residual model nondeterminism), demonstrating the
  semantic layer suppresses the re-report at the prompt.
- **PATTERN**: `tests/test_multipass_live.py` (import via conftest gate; `config.BASELINE_MODEL`).
- **GOTCHA**: haiku tier; keep it a single focused assertion to bound cost. Do NOT assert on prose.
- **VALIDATE**: `../../.venv/bin/python -m pytest -m integration tests/test_dedupe_semantic_live.py -q`
  (run once; expensive — not part of `make test`).

### UPDATE `tests/test_post.py` — skip-by-default real-`gh` test (optional integration)

- **IMPLEMENT**: `@pytest.mark.integration` + `@pytest.mark.skipif` (skip unless both `shutil.which(
  "gh")` and an env var like `CI_REVIEW_LIVE_PR` are set) test that actually posts to the PR named by
  the env var and asserts a 0 returncode. Skip-by-default: there is no live PR in the MVP, so this
  documents the real path without requiring it.
- **VALIDATE**: `../../.venv/bin/python -m pytest -m integration tests/test_post.py -q` (skips cleanly
  when the env var is unset).

### UPDATE `_tasks/todo.md`

- **IMPLEMENT**: Add a `## Phase 4 — Trust Loop (TR9 / FR4 + gh --post + semantic dedupe)` section
  with the task checklist, the seed-vs-runtime store deviation note, and (after execution) the
  Validation results + Review sections in the established house style.
- **VALIDATE**: visual — section present, checkboxes reflect completion.

---

## TESTING STRATEGY

Mirror the project's offline-first discipline: every pure function is unit-tested with hand-authored
`Finding` lists and no shell-out; live behavior is `integration`-marked and excluded from `make test`.

### Unit Tests (offline — `-m "not integration"`)
- **`test_instrument.py`** (new): store round-trip; `record_emitted`/`record_dismissal` (increment +
  no-mutation); `category_dismissal_rates`; `auto_quarantined` threshold + min-sample gate;
  `quarantined_categories` (auto ∪ manual); **`apply_quarantine` FR4 headline** (quarantine two
  categories, the other two survive); seed regression-lock.
- **`test_post.py`** (extend): `format_review_body` location coverage; `build_gh_comment_args` shape
  (±repo); `post_via_gh` dry-run never shells out; executes-when-not-dry-run via injected fake runner.
- **`test_dedupe.py`** (extend): `render_prior_findings` sentinel + stable listing.
- **`test_cli.py`** (extend): prompt carries prior findings; quarantine filters before emit; default
  path unchanged with absent store; `--post` requires `--pr`; `--post --dry-run` prints gh argv.

### Integration Tests (marked; NOT in `make test`)
- **`test_dedupe_semantic_live.py`** (new): two-run multipass with prior injected → 0 new `none-deref`
  comments (semantic-layer proof), haiku tier.
- **`test_post.py`** real-`gh` test: skip-by-default (needs `gh` + `CI_REVIEW_LIVE_PR`).

### Edge Cases (must be covered)
- Absent runtime dismissal store → `quarantined_categories == []` → default emit path unchanged.
- Category with Σemitted == 0 → excluded from rate (no ZeroDivision).
- Rare-but-100%-dismissed category (`security` 2/2) → NOT auto-quarantined (min-sample guard).
- `manual_quarantine` forces a category regardless of rate/sample.
- Empty `prior` → sentinel text; token still resolves (no leftover `{prior_findings}` in the prompt).
- `--post` with a nonzero `gh` returncode → surfaced as a clear stderr note + nonzero exit.
- Baseline prompt (no `{prior_findings}` token) + `--pr-id` → `.replace` is a no-op (no crash).

---

## VALIDATION COMMANDS

Execute in order; each must pass before moving on.

### Level 1: Syntax
```
../../.venv/bin/python -m py_compile src/review/instrument.py src/review/post.py src/review/cli.py src/review/multipass.py src/review/dedupe.py src/review/config.py
../../.venv/bin/python -c "import json; json.load(open('fixtures/dismissed_patterns.seed.json'))"
```

### Level 2: Offline unit suite (must grow from 113 and stay green)
```
make test-unit
```

### Level 3: Integration (run once; expensive; haiku)
```
../../.venv/bin/python -m pytest -m integration tests/test_dedupe_semantic_live.py -q
```

### Level 4: Manual / demo validation
```
make quarantine-demo    # OFFLINE: prints quarantined=[maintainability,performance]; correctness+security survive
make post-dry-run       # OFFLINE: prints "DRY RUN — would run: gh pr comment 1 --body ..."; posts nothing
make dedupe-demo        # LIVE multipass x2: "duplicate comments on re-run" should now be 0 (was 1)
```

### Level 5: No-regression on the default path + clean import surface
```
make ci-review PR=fixtures/pr-01/sample.diff < /dev/null   # exit 0, 1 finding, no hang, no quarantine note
grep -rEn "import anthropic|claude_agent_sdk|from anthropic" src/ && echo "LEAK" || echo "clean"
git check-ignore data/dismissed_patterns.json
```

---

## ACCEPTANCE CRITERIA

- [ ] `instrument.py` tracks dismissals by `detected_pattern` and computes per-category dismissal rate.
- [ ] A category over the rate threshold (with enough samples) is auto-quarantined; a manual override
      list also quarantines; a rare high-rate category is protected by the min-sample guard.
- [ ] **Quarantining one category filters exactly its findings; every other category still emits**
      (the FR4 gate), proven deterministically offline in `test_instrument.py`.
- [ ] `--post` posts via `gh` only when `--pr` is supplied; `--post --dry-run` prints the exact `gh`
      argv and posts nothing; the argv builder is unit-tested; emit remains the default.
- [ ] The enriched + integration prompts carry `{prior_findings}`; `cli.py`/`multipass.py` inject
      rendered prior findings; the baseline prompt is untouched.
- [ ] `make dedupe-demo` reports **0** duplicate comments on re-run (the cross-end drift is resolved).
- [ ] `make ci-review PR=fixtures/pr-01/sample.diff` is byte-for-byte unchanged (default path preserved).
- [ ] Offline suite grows and stays green; grep for `anthropic`/`claude_agent_sdk` stays clean.
- [ ] `data/dismissed_patterns.json` is gitignored; the seed lives under `fixtures/`.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order; each task's VALIDATE ran green.
- [ ] Levels 1-5 all pass.
- [ ] Offline unit suite passes (count recorded in `_tasks/todo.md`).
- [ ] The one semantic-layer integration test passed once (result recorded).
- [ ] No `anthropic`/`claude-agent-sdk`/library-`gh` imports.
- [ ] `_tasks/todo.md` updated with results + a Review section (what worked / didn't / deviations).
- [ ] Default `ci-review` path confirmed unchanged.

---

## NOTES

**Design decisions & trade-offs**

1. **Quarantine granularity = category (lever), tracked by pattern (evidence).** Matches user story 8
   ("disable the noisy category"). Dismissals accrue per `detected_pattern` (fine-grained evidence);
   the rate is aggregated to the finding's `category` (the 4-value controlled set) which is the unit
   the filter acts on. A min-sample guard (`QUARANTINE_MIN_SAMPLE`) prevents one or two dismissals
   from nuking an entire category — important because categories are coarse.

2. **Seed store under `fixtures/`, runtime store under `data/` (gitignored).** The PRD names
   `data/dismissed_patterns.json`; that stays the runtime path. But a file that is BOTH committed
   (demo input) AND mutated at runtime causes git churn and non-reproducible demos. Splitting them
   (committed `fixtures/dismissed_patterns.seed.json` for the deterministic offline demo; gitignored
   `data/dismissed_patterns.json` for accrued runtime dismissals) is the clean resolution. Documented
   deviation.

3. **`gh` posting = `gh pr comment`, not line-anchored review comments.** A true inline review comment
   needs the PR head commit SHA (`gh api repos/{owner}/{repo}/pulls/{n}/comments`), which is NOT
   derivable from a bare diff file. `gh pr comment` needs only the PR number and works today; the
   finding body carries `file:line` so location is preserved in the posted text. The `gh api` inline
   variant is a noted extension, not built (there is no live PR in the MVP anyway). This keeps `--post`
   real, testable (argv builder + dry-run), and honest about scope.

4. **Semantic layer + prior accumulation.** Feeding prior findings into the prompt is what resolves
   the cross-end drift (`ingest.py` vs `summary.py`): once the producer-end report is in the prompt,
   the model won't re-report the same defect at the consumer end. Persisting `dedupe(prior + current)`
   (accumulate, then structural-dedupe) ensures a previously-reported issue is never dropped from the
   memory just because the model chose not to repeat it. The structural `suppress_prior` remains the
   deterministic backstop — the two layers are belt-and-suspenders, exactly like the severity design.

5. **Offline-first everywhere.** The quarantine demo and every quarantine/dedupe/post-builder
   assertion run with no `claude -p` and no key. Only two things need the CLI: the (single) semantic
   integration test and `make dedupe-demo`. This matches the project's principle 5 (validation is
   structural, never editorial) and keeps `make test` fast and hermetic.

**Confidence score for one-pass success: 8/10.** The pure cores (instrument, render, gh builder) and
their offline tests are low-risk and fully specified against verified idioms. The main risks: (a)
`cli.py` wiring has several insertion points (prompt compose, prior accumulation, quarantine filter,
post branch) that must not disturb the byte-for-byte default path — Level 5 guards this; (b) the
`--repo`/`--gh-repo` distinction is easy to fumble; (c) `make dedupe-demo` reaching exactly 0 depends
on live-model behavior (haiku) — if it lands at 0 for `none-deref` but the cross-file end still
occasionally drifts, record the honest number and rely on the deterministic offline dedupe tests as
the true gate (the Phase-3a review already set this precedent).
