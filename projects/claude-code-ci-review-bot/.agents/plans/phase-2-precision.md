# Feature: Phase 2 — Precision (TR3 / TR4 / TR5 + FR4-precursor)

The following plan should be complete, but it's important that you validate documentation and codebase
patterns and task sanity before you start implementing. Pay special attention to naming of existing utils,
types, and models (from Phase 1) — **import from the right files**, and do not reshape the Phase 1 contract.

> **HARD PREREQUISITE — read this first.** As of writing, **Phase 1 is NOT implemented** — only
> `.agents/plans/phase-1-headless-structured.md` exists; there is no `src/`, `Makefile`, `requirements.txt`, or
> `pytest.ini` on disk. This plan builds directly on Phase 1's spine (`config.py`, `schema.py`, `runner.py`,
> `parse.py`, `post.py`, `cli.py`). **You must execute Phase 1 first** (`/core_piv_loop:execute` on the Phase 1
> plan) and confirm its acceptance criteria pass. Because Phase 1 code does not yet exist, the file:line
> references below to Phase-1 modules point at the **Phase 1 plan's specified interfaces**, not real lines —
> **the very first task of this plan re-verifies those interfaces against the actual Phase 1 code** and adapts
> if they drifted.

> **Ground-truth already established during planning (do not re-derive):**
> - Claude Code **2.1.193** is on PATH. `claude -p` **auto-loads `CLAUDE.md` from the working directory and
>   every ancestor directory up to `/`**, plus `~/.claude/CLAUDE.md` (user) and any managed-policy file. This is
>   the TR3 mechanism — **and its trap** (see §"TR3 mechanism" below). `--output-format json` / `--json-schema`
>   do **not** affect memory loading. `--bare` disables ALL CLAUDE.md auto-discovery (verified via `claude
>   --help`); we use it only as a documented fallback, not on the core path.
> - Sibling house style verified live: pure/total/deterministic stdlib-only modules, **string constants (not
>   enums)**, `#:` doc-comments on constants, dataclass result structs, `conftest.py` puts `src/` on
>   `sys.path` + `skipif` gates live tests. Neither sibling has a `Makefile` (ours is defined by the Phase 1
>   plan).

---

## Feature Description

Phase 2 turns the Phase-1 plumbing spine ("it runs headless and parses") into a **precise reviewer developers
trust**. It adds the four things that move the trust needle:

1. **A seeded fixture repo** (`fixtures/sample-repo/`) that is *ground truth*: a genuine bug that **must** be
   flagged, a convention-dependent pattern that **must not** be flagged, and a cross-file data-flow bug that a
   single-pass review is *expected to miss* (it's Phase 3's integration-pass target — seeded now).
2. **The reviewed project's `CLAUDE.md`** (`fixtures/sample-repo/CLAUDE.md`) as the bot's runtime context
   channel (**TR3**) — carrying project conventions, review criteria, and the severity rubric, so a run gains
   project context **without hand-pasting it into the prompt string**.
3. **An enriched, versioned review prompt** (`.claude/commands/review/review-diff.md`) with **explicit
   flag/don't-flag criteria + few-shot pairs** (**TR4**) and a **severity rubric where each level carries a
   concrete code example** (**TR5**) — the primary false-positive lever.
4. **A precision/recall harness** (`make metrics`) that scores findings against the fixture ground truth and
   reports the headline trust number **before vs. after** TR4/TR5, plus a **TR3 present-vs-absent** behavior
   change and a **severity-consistency** check across two PRs.

Phase 2 is deliberately **still single-pass**. Multi-pass / independent instance (TR6/TR7), dedupe (TR8),
test-gen (FR2), `detected_pattern` quarantine (TR9/FR4), and real `gh --post` are **out of scope** (Phases 3–4).

## User Story

As a **wary senior engineer who has muted noisy review bots**,
I want the bot to **flag the genuine bug, stay silent on our project's convention-dependent code, label severity
identically across PRs, and prove it with a precision/recall number**,
So that **I trust and act on its findings instead of muting it** — and so my team can tune review criteria
through our project's `CLAUDE.md` rather than editing pipeline code.

## Problem Statement

Phase 1 proves the pipeline *runs* and *parses*, but a bot that emits noise gets muted, and one noisy category
poisons trust in every other finding (PRD §1). There is currently **no measurement of precision**, **no project
context channel** (criteria would have to be hand-pasted into `-p`, violating TR3), **no severity consistency
mechanism** (the same issue class could be labeled differently across PRs), and **no fixture** to gate any of
this. Without a ground-truth harness, "the bot is good" is prose, not proof.

## Solution Statement

Build the ground-truth fixture + its `CLAUDE.md`, enrich the versioned prompt with explicit criteria/few-shot/
severity examples, add a **pure, deterministic `severity.py`** (normalization + a canonical `pattern→severity`
override that makes severity *identical across PRs* regardless of model whim), and a **pure, deterministic
`metrics.py`** scorer wrapped by a thin live driver + `make metrics`. Crucially, run every review inside a
**staged temp workspace outside the monorepo** so the *only* project memory the model sees is the fixture's own
`CLAUDE.md` — cleanly isolating the TR3 A/B and preventing the bot-dev `CLAUDE.md` from leaking into the review
(PRD Risk #3). All scoring/normalization logic is stdlib-only and unit-tested offline; live model calls are
`integration`-marked and use a cheap tier.

## Feature Metadata

**Feature Type**: Enhancement (adds precision engineering + measurement onto the Phase-1 spine)
**Estimated Complexity**: Medium–High (low algorithmic complexity; the hard parts are the TR3 isolation design,
prompt calibration against a real model, and building an honest ground-truth harness)
**Primary Systems Affected**: `.claude/commands/review/` (enrich), `src/review/` (new `severity.py`,
`metrics.py`, `workspace.py`; modify `runner.py`, `cli.py`, `config.py`), `fixtures/sample-repo/` (new),
`data/metrics/` (new), `tests/` (new unit + integration), `Makefile` (new targets)
**Dependencies**: none new — `jsonschema`, `python-dotenv`, `pytest` already installed in the shared venv
(`../../.venv`). Claude Code CLI 2.1.193 on PATH is the agent under test.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**Phase-1 code (in THIS repo — read the ACTUAL files once Phase 1 is executed; interfaces summarized from the
Phase 1 plan):**
- `src/review/config.py` — env `load_env()` (idempotent, `.env` at `parents[4]`), `REVIEW_MODEL`
  (`"claude-sonnet-4-6"`), `CLAUDE_TIMEOUT_S` (300), `PROMPT_TEMPLATE` (path to `review-diff.md`),
  `anthropic_key_present()`. Why: you extend it with fixture/metrics/baseline constants; **reuse `load_env`,
  don't re-invent**.
- `src/review/schema.py` — `FINDINGS_SCHEMA` (dict), `as_json_string()`, `validate_findings_obj(obj)`. Why: the
  canonical contract already includes `severity` (enum), `detected_pattern`, `category`. Phase 2 does **not**
  change the schema shape.
- `src/review/parse.py` — `Location(file,line)`, `Finding(location, issue, severity, suggested_fix,
  detected_pattern, category)`, `ParsedReview(findings, is_error, terminal_reason, raw)`,
  `parse_result(stdout)`, `ParseError`. Why: `severity.py`/`metrics.py` operate on `Finding` objects — import
  these, don't redefine.
- `src/review/runner.py` — `invoke_claude(prompt, schema_json, model, timeout_s) -> RunResult(stdout, stderr,
  returncode)`. Why: **you add a `cwd` parameter** (the TR3 lever). Keep the signature backward-compatible
  (`cwd: str | None = None`).
- `src/review/post.py` — `format_comment(finding)`, `emit(findings)`. Why: unchanged behavior; `cli.py` calls
  `emit` after severity normalization.
- `src/review/cli.py` — argparse entrypoint (`--diff`, `--model`), frontmatter-strip + `.replace("{diff}", …)`
  prompt composition. Why: you add prompt-variant selection + apply canonical severity before `emit`.
- `.claude/commands/review/review-diff.md` — the minimal Phase-1 prompt. Why: you **snapshot it to
  `review-diff.baseline.md`** (the "before" arm), then enrich `review-diff.md`.
- `CLAUDE.md` (this repo) — the **two-CLAUDE.md rule** (dev-guidance here vs. the fixture's runtime context) and
  **CLI-as-agent, no SDK** rule. Why: the fixture `CLAUDE.md` you write is role #2; never conflate them.
- `PRD.md` (§10 finding schema lines 280–314; §12 Phase 2 lines 353–361; §6 dir structure lines 154–190). Why:
  canonical layout + the exact Phase 2 deliverable list and validation gates.
- `docs/04-claude-code-ci-review-bot.md` (TR3 lines 40–41, TR4 lines 42–44, TR5 lines 45–46; acceptance lines
  78–84). Why: the non-negotiable requirements this phase satisfies.

**Sibling house-style references (mirror EXACTLY — verified live during planning):**
- `../multi-agent-research-agent/src/coverage_eval.py` (whole file, esp. lines 28–135) — Why: the **canonical
  template** for `severity.py` and `metrics.py`: module docstring stating "pure, total, deterministic,
  stdlib-only, never raises"; **string constants** (`STATUS_COVERED = "covered"`, lines 30–35); a lenient
  `_normalize_status(raw)` that coerces unknowns to a safe default (lines 80–83); `@dataclass` result struct
  (`CoverageResult`, lines 51–57); an alias `dict[str, tuple[str, ...]]` where **insertion order matters**
  (lines 40–45). **Copy this style.**
- `../multi-agent-research-agent/src/config.py` (lines 14–58) — Why: model-tier constants with `#:` doc-comments
  citing the TR they serve (e.g. `CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"`, lines 24–28); env loader at
  `parents[N]`. Mirror the `#:` comment discipline for the new constants.
- `../multi-agent-research-agent/tests/conftest.py` (whole file) — Why: `src` on `sys.path` (lines 16–19),
  `config.load_env()` at collection (line 23), the `shutil.which("claude") … or config.anthropic_key_present()`
  capability gate (lines 26–34). **Phase 2's conftest extends the Phase-1 conftest** (which puts `src/review` on
  the path — one level deeper than the sibling); add a `ground_truth` fixture and a `sample_findings` fixture.
- `../multi-agent-research-agent/tests/test_coverage.py` (whole file) — Why: the **exact unit-test shape** to
  mirror for `test_severity.py` / `test_metrics.py`: module-level fixture strings, `@pytest.mark.parametrize`
  tables (lines 117–132), assertions on **structure/constants, never prose**.
- `../multi-agent-research-agent/src/triage.py` (lines 32–58) — Why: precedent for **string route/label
  constants + heuristic tables** (not enums), directly applicable to `SEVERITY_LEVELS` / `PATTERN_SEVERITY`.
- `../customer-support/src/mocks/fixtures.py` (lines 15–98) — Why: house pattern for **seed data with
  deliberately-staged shapes + an intent comment** explaining *why* each case exists. The fixture source files'
  header comments should follow this "explain the seeded intent" convention.

### New Files to Create

```
claude-code-ci-review-bot/
├── .claude/commands/review/
│   ├── review-diff.md                      # ENRICH: explicit criteria + few-shot + severity rubric (TR4/TR5)
│   └── review-diff.baseline.md             # SNAPSHOT of the Phase-1 minimal prompt (the "before" arm)
├── src/review/
│   ├── severity.py                         # NEW: normalize + canonical pattern→severity override (TR5)
│   ├── metrics.py                          # NEW: pure scorer (findings vs ground_truth) + live driver (TR4/TR5)
│   └── workspace.py                        # NEW: stage a review workspace in $TMPDIR (TR3 isolation)
├── fixtures/sample-repo/
│   ├── CLAUDE.md                           # NEW: the bot's RUNTIME context channel (TR3) — criteria+conventions
│   ├── src/orders.py                       # seeded REAL bug: None-deref (MUST flag, high, correctness)
│   ├── src/pricing.py                      # convention-dependent: pct-as-fraction (MUST NOT flag — TR3 lever)
│   ├── src/ingest.py                       # cross-file producer (writes key "user_id")
│   ├── src/summary.py                      # cross-file consumer (reads "userId") → runtime KeyError
│   ├── pr.diff                             # the "PR": a unified diff touching all four src files
│   ├── pr-02.diff                          # a SECOND PR re-introducing the None-deref class (severity-consistency)
│   └── ground_truth.json                   # the answer key (NEVER staged into the model's workspace)
├── data/metrics/                           # results store: baseline.json / enriched.json / tr3-demo.json
│   └── .gitkeep
└── tests/
    ├── test_severity.py                    # OFFLINE: normalization + canonical override
    ├── test_metrics.py                     # OFFLINE: scorer TP/FP/FN/precision/recall vs ground_truth
    ├── test_workspace.py                   # OFFLINE: staging includes CLAUDE.md, EXCLUDES ground_truth.json
    └── test_precision_live.py              # [integration] real reviews on the fixture: the acceptance demos
```

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Claude Code Memory / CLAUDE.md loading](https://code.claude.com/docs/en/memory) — Why: authoritative on the
  tree-walk load order (managed policy → `~/.claude/CLAUDE.md` → ancestors root→cwd → nested on-demand). **This
  is why the fixture must be staged OUTSIDE the monorepo** — otherwise the bot-dev `CLAUDE.md` and
  `~/.claude/CLAUDE.md` leak into every review.
- [Claude Code Headless mode](https://code.claude.com/docs/en/headless) — Why: `-p` / `--output-format` /
  `--json-schema` reference (Phase-1 already proved these; unchanged here).
- No new external library docs — `jsonschema`, `subprocess`, `tempfile`, `shutil` usage is stdlib and shown
  inline below.

### TR3 mechanism (the crux — and its trap)

`claude -p` gains project context by **auto-loading `CLAUDE.md` from `cwd` and every ancestor**. Naively running
with `cwd=fixtures/sample-repo/` would load, in order: managed policy → `~/.claude/CLAUDE.md` (Sandeep's global
dev prefs) → `.../claudemuse/CLAUDE.md`? → `.../projects/…?` → **`claude-code-ci-review-bot/CLAUDE.md` (the
BOT-DEV guidance — "don't import claude-agent-sdk", etc.)** → `fixtures/sample-repo/CLAUDE.md`. That is exactly
the **two-CLAUDE.md-conflated** failure (PRD Risk #3): dev guidance contaminates the review.

**Chosen isolation:** run every review inside a **staged temp workspace under `$TMPDIR`** (outside the
monorepo). Walking up from `$TMPDIR` finds **no project `CLAUDE.md`** (only the constant `~/.claude` +
managed-policy layers). Therefore the **only project-level memory delta between the two TR3 arms is the
fixture's own `CLAUDE.md`** — a clean, controlled A/B:
- **present arm:** staged dir **contains** `CLAUDE.md` → auto-loaded.
- **absent arm:** staged dir **omits** `CLAUDE.md` → no fixture memory.
Both arms are otherwise identical (same enriched prompt, same model, same diff, same `~/.claude` layer), so any
behavior change is attributable to the fixture `CLAUDE.md`. (Fallback if staging ever proves insufficient:
`--bare` for the absent arm; but prefer the controlled toggle — `--bare` also strips hooks/plugins/user memory,
confounding the delta.)

> **CRITICAL GOTCHA — the answer key must never reach the model.** `ground_truth.json` and the `*.diff` files
> are the *evaluation* artifacts; `workspace.py` MUST exclude them from the staged dir, or the model could read
> the answers (tools aren't granted in P2, but exclude them anyway — defense in depth, and P3 grants Read).

### Patterns to Follow

**Naming (Python — snake_case; the global camelCase rule is JS-specific and does not apply):** functions/vars
`snake_case`, dataclasses/types `PascalCase`, module constants `UPPER_SNAKE`. String constants, **not enums**
(sibling precedent: `coverage_eval.STATUS_*`, `triage.ROUTE_*`).

**Pure-module docstring + design contract (mirror `coverage_eval.py:1–26`):** open each new pure module with a
docstring stating it is *pure, total, deterministic, stdlib-only, never raises*, and *unit-tests without
credentials*.

**Constants with `#:` doc-comments citing the TR (mirror `config.py:14–53`):**
```python
#: Canonical severity order, highest→lowest. The single source of truth for ranking/sorting (TR5).
SEVERITY_LEVELS: tuple[str, ...] = ("critical", "high", "medium", "low")
```

**Lenient normalization with a safe default (mirror `coverage_eval._normalize_status`, lines 80–83):**
```python
def normalize_severity(raw: str) -> str:
    s = (raw or "").strip().lower()
    return s if s in _SEVERITY_SET else _SEVERITY_ALIASES.get(s, "medium")
```

**Alias/override table where insertion determinism matters (mirror `coverage_eval.FACET_ALIASES`, lines 40–45):**
a plain `dict[str, str]` for `PATTERN_SEVERITY`, matched by exact `detected_pattern` key (no substring
ambiguity — unlike facets, patterns are our own controlled slugs).

**Result dataclass (mirror `CoverageResult`, lines 51–57):**
```python
@dataclass
class MetricsResult:
    tp: int; fp: int; fn: int
    precision: float; recall: float; f1: float
    matched: list; false_positives: list; missed: list  # for human-readable reporting
```

**Test path/import setup (mirror `conftest.py:16–34`, adjusted to `src/review`):** Phase-1 conftest already
inserts `src/review` on `sys.path` and calls `config.load_env()`; extend it, don't duplicate. Gate live tests
with `shutil.which("claude") is not None or config.anthropic_key_present()`.

**Assert on structure/outcomes, never model wording (PRD principle 5; `test_coverage.py` throughout).**

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (verify P1, then contracts)
Confirm the Phase-1 spine is real and its interfaces match this plan; add the pure `severity.py` and the
staging helper before any I/O or fixtures.
**Tasks:** verify P1 interfaces; extend `config.py`; `severity.py`; `workspace.py`.

### Phase 2: Fixture & Prompt (the ground truth + the lever)
Build the seeded fixture repo, its `CLAUDE.md` (TR3), `ground_truth.json`, the diffs, snapshot the baseline
prompt, and enrich the review prompt (TR4/TR5).
**Tasks:** fixture source files; `pr.diff` / `pr-02.diff`; `ground_truth.json`; `fixtures/sample-repo/CLAUDE.md`;
`review-diff.baseline.md`; enriched `review-diff.md`.

### Phase 3: Scoring & Integration (measurement)
The pure scorer + the live driver + `runner.cwd` + CLI wiring + Make targets.
**Tasks:** `runner.py` (`cwd`); `metrics.py` (pure scorer + live driver); `cli.py` (prompt variant + canonical
severity); `Makefile` (`metrics`, `tr3-demo`).

### Phase 4: Testing & Validation
Offline unit suite (severity, metrics scorer, workspace-exclusion) + the live acceptance demos + record the
before/after number.
**Tasks:** `test_severity.py`; `test_metrics.py`; `test_workspace.py`; `test_precision_live.py`; run the
metrics + TR3 demo; update `_tasks/todo.md`.

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task is atomic and independently testable. `PY=../../.venv/bin/python`.

### VERIFY Phase-1 interfaces (do this FIRST — do not skip)
- **IMPLEMENT**: Confirm Phase 1 is executed and its acceptance criteria pass. Read the ACTUAL
  `src/review/{config,schema,parse,runner,post,cli}.py` and reconcile the exact names/signatures with the
  "Phase-1 code" list above (esp. `Finding` field order, `invoke_claude` params, `parse_result` return type).
  If anything drifted, adapt the tasks below to the real names — **the real code wins over this plan.**
- **GOTCHA**: If `src/review/` doesn't exist, STOP and execute `.agents/plans/phase-1-headless-structured.md`
  first. This plan cannot be implemented against a nonexistent spine.
- **VALIDATE**: `$PY -m pytest -m "not integration" -q` (Phase-1 offline suite green) and
  `PYTHONPATH=src/review $PY -c "import config,schema,parse,runner,post; from parse import Finding,Location; print('P1 OK', [f for f in Finding.__dataclass_fields__])"`

### CONFIRM the TR3 auto-load assumption (cheap live probe — de-risks the whole phase)
- **IMPLEMENT**: A throwaway 2-run probe proving `CLAUDE.md` in `cwd` changes behavior. In a fresh `$TMPDIR`
  dir, run `claude -p "What is our project's mascot? Answer in one word."` once with a `CLAUDE.md` containing
  "Our project mascot is the Platypus." and once without it; confirm the answer differs. Use
  `--model claude-haiku-4-5-20251001` to cap cost.
- **GOTCHA**: This validates the *mechanism* only. If the present-arm does NOT pick up the file, the fallback is
  `--add-dir <staged-dir>` or (last resort) `--append-system-prompt` — but do not switch off the auto-load path
  without proving it's broken; the docs and version (2.1.193) say it works.
- **VALIDATE**: run the two commands; assert the two answers differ (present mentions "platypus", absent does
  not). Delete the probe dir afterward.

### UPDATE `src/review/config.py`
- **IMPLEMENT**: ADD constants (with `#:` doc-comments citing the TR), grouped after the Phase-1 constants:
  - `BASELINE_MODEL = "claude-haiku-4-5-20251001"` — metrics/integration tier to cap cost (mirror sibling
    `CLASSIFIER_MODEL`); `REVIEW_MODEL` stays the production default.
  - `PROJECT_ROOT = Path(__file__).resolve().parents[2]` (if not already present from P1).
  - `FIXTURE_REPO = PROJECT_ROOT / "fixtures" / "sample-repo"`.
  - `GROUND_TRUTH = FIXTURE_REPO / "ground_truth.json"`.
  - `BASELINE_PROMPT = PROJECT_ROOT / ".claude/commands/review/review-diff.baseline.md"`.
  - `ENRICHED_PROMPT = PROJECT_ROOT / ".claude/commands/review/review-diff.md"` (alias of P1 `PROMPT_TEMPLATE`
    — reuse the existing constant if named differently; do not duplicate).
  - `METRICS_DIR = PROJECT_ROOT / "data" / "metrics"`.
  - `LINE_MATCH_TOLERANCE = 3` — a finding matches a ground-truth case if same file and `|line - case.line| <=`
    this (models report hunk lines ±a few).
- **PATTERN**: `../multi-agent-research-agent/src/config.py:14–58` (`#:` comments + `parents[N]` paths).
- **IMPORTS**: `from pathlib import Path` (already imported in P1).
- **GOTCHA**: `parents[2]` = project root from `src/review/config.py` (P1 uses `parents[4]` for `.env` — a
  different walk; don't confuse them).
- **VALIDATE**: `PYTHONPATH=src/review $PY -c "import config; print(config.FIXTURE_REPO.name, config.BASELINE_MODEL, config.LINE_MATCH_TOLERANCE)"`
  → expect `sample-repo claude-haiku-4-5-20251001 3`

### CREATE `src/review/severity.py`
- **IMPLEMENT**: A **pure, total, deterministic, stdlib-only** module (docstring says so; never raises):
  - `SEVERITY_LEVELS: tuple[str,...] = ("critical","high","medium","low")`; `_SEVERITY_SET = set(SEVERITY_LEVELS)`.
  - `_SEVERITY_ALIASES: dict[str,str]` mapping likely off-vocabulary words to canonical (e.g. `"blocker":
    "critical"`, `"error":"high"`, `"warning":"medium"`, `"warn":"medium"`, `"info":"low"`, `"nit":"low"`,
    `"minor":"low"`).
  - `normalize_severity(raw: str) -> str` — lowercase/strip → canonical if in set → alias → default `"medium"`.
  - `SEVERITY_RANK: dict[str,int]` = `{lvl: i for i, lvl in enumerate(SEVERITY_LEVELS)}` (0 = most severe);
    `severity_rank(sev) -> int` = `SEVERITY_RANK[normalize_severity(sev)]`.
  - `PATTERN_SEVERITY: dict[str,str]` — the **TR5 determinism lever**: canonical severity per known
    `detected_pattern` slug (e.g. `"none-deref":"high"`, `"cross-file-key-mismatch":"critical"`,
    `"timing-unsafe-comparison":"high"`). Keys are OUR controlled slugs (exact match, no substrings).
  - `canonical_severity(finding) -> str` — if `finding.detected_pattern` in `PATTERN_SEVERITY` return that
    (overrides the model), else `normalize_severity(finding.severity)`.
  - `apply_canonical_severity(findings: list[Finding]) -> list[Finding]` — return NEW `Finding`s with
    `severity` replaced by `canonical_severity(f)` (use `dataclasses.replace`); pure, no mutation.
  - `sort_by_severity(findings) -> list[Finding]` — sorted by `severity_rank` then file/line (stable, for
    readable emit order).
- **PATTERN**: `../multi-agent-research-agent/src/coverage_eval.py:30–45,80–83` (string constants + lenient
  normalize + ordered table); `src/triage.py:32–58` (label-constant style).
- **IMPORTS**: `from dataclasses import replace`; `from parse import Finding` (flat import — `src/review` is on
  path). **Do NOT import `runner`/`subprocess`** — this module must be importable offline with no CLI.
- **GOTCHA**: `PATTERN_SEVERITY` is the mechanism that makes "severity identical for the same issue class across
  two PRs" **deterministic** rather than hoping the model is consistent. The prompt rubric (TR5) is the
  *primary* lever (it shapes what the model emits); `apply_canonical_severity` is the *backstop* that guarantees
  the acceptance gate. Document this two-layer relationship in the module docstring.
- **VALIDATE**: `PYTHONPATH=src/review $PY -c "from parse import Finding,Location; import severity; f=Finding(Location('a.py',1),'x','low','fix','none-deref','correctness'); print(severity.canonical_severity(f), severity.normalize_severity('BLOCKER'), severity.severity_rank('warn'))"`
  → expect `high critical 2`

### CREATE `src/review/workspace.py`
- **IMPLEMENT**: A small helper that stages a **clean review workspace outside the monorepo** (the TR3 isolation
  + answer-key exclusion):
  - `STAGE_EXCLUDE = {"ground_truth.json"}` and exclude glob suffixes `.diff` — the answer key + eval artifacts
    must never be visible to the model.
  - `stage_workspace(fixture_dir: Path, include_claude_md: bool = True) -> Path`:
    1. `dest = Path(tempfile.mkdtemp(prefix="ci-review-"))` (under `$TMPDIR`, outside the monorepo).
    2. Copy `fixture_dir` tree into `dest`, skipping any file in `STAGE_EXCLUDE` or ending `.diff`, and — if
       `include_claude_md` is False — also skipping `CLAUDE.md`.
    3. Return `dest`.
  - `cleanup_workspace(path: Path) -> None` — `shutil.rmtree(path, ignore_errors=True)`; guard that `path` is
    under the system temp dir before removing (never rmtree inside the repo).
  - Prefer a context manager `staged(fixture_dir, include_claude_md)` (`@contextmanager`) yielding `dest` and
    cleaning up in `finally`, so callers can't leak temp dirs.
- **PATTERN**: stdlib `tempfile`/`shutil`; pure-ish, unit-testable (no CLI). Follow the "explain the seeded
  intent" comment discipline from `../customer-support/src/mocks/fixtures.py:25–44`.
- **IMPORTS**: `tempfile`, `shutil`, `from pathlib import Path`, `from contextlib import contextmanager`.
- **GOTCHA**: Use `shutil.copytree(..., ignore=shutil.ignore_patterns("*.diff", "ground_truth.json"))` for the
  exclusion in one shot; then conditionally delete `CLAUDE.md`. **Never** `rmtree` a path that isn't under
  `tempfile.gettempdir()` — assert it before removing (a footgun guard, per global "never delete without care").
- **VALIDATE**: `PYTHONPATH=src/review $PY -c "import workspace,config; d=workspace.stage_workspace(config.FIXTURE_REPO, True); import os; files=set(os.listdir(d)); print('CLAUDE.md' in files or (d/'CLAUDE.md').exists(), 'ground_truth.json' not in files); workspace.cleanup_workspace(d)"`
  (run AFTER the fixture exists) → expect `True True`

### CREATE `fixtures/sample-repo/src/orders.py` (the REAL bug — MUST flag)
- **IMPLEMENT**: A small module with **one unambiguous, general bug**: a **None-deref on a realistic path**.
  E.g. `def greet_user(uid, db): user = db.get(uid); return f"Hello {user.name}"` — when `uid` is absent
  `db.get` returns `None` and `user.name` raises `AttributeError`. Keep the file ~20 lines with a header comment
  stating the seeded intent ("SEEDED: None-deref, must be flagged; ground-truth case `none-deref`"). This bug is
  **general** (no project convention needed) so BOTH baseline and enriched prompts should catch it → keeps
  recall high; precision is what moves.
- **PATTERN**: `../customer-support/src/mocks/fixtures.py:25–44` intent-comment convention.
- **GOTCHA**: the seeded bug's line in `pr.diff`'s NEW-file numbering must be knowable → keep it on an obvious
  line. Do NOT also seed subtle secondary bugs here (keep one signal per file for clean scoring).
- **VALIDATE**: `$PY -m py_compile fixtures/sample-repo/src/orders.py`

### CREATE `fixtures/sample-repo/src/pricing.py` (convention-dependent — MUST NOT flag; the TR3 lever)
- **IMPLEMENT**: Code that looks buggy by GENERAL standards but is CORRECT under a project convention stated
  ONLY in the fixture `CLAUDE.md`. Recommended: **percentages stored as fractions `0.0–1.0`**:
  `def net_price(price, discount_rate): return price * (1 - discount_rate)` with a docstring noting
  `discount_rate` is a fraction. Without the convention, a reviewer reasonably flags "discount_rate not divided
  by 100 — likely a bug." With the `CLAUDE.md` convention ("all rates/percentages are fractions 0.0–1.0;
  dividing by 100 would be the bug"), it's correct → **must not flag.** This is the TR3 delta AND the
  idiomatic-but-unusual case in one. (Backup if the delta proves weak empirically: a `Settings.get()` that
  swallows all exceptions and returns a schema default, with `CLAUDE.md` declaring "settings reads must never
  raise.")
- **PATTERN**: same intent-comment convention; header states "SEEDED: convention-dependent correctness; must
  NOT be flagged when CLAUDE.md present; ground-truth case `pct-as-fraction` (should_flag=false)."
- **GOTCHA**: This case must be something the **generic** enriched few-shot cannot pre-empt — it must require
  the *project-specific* rule. Do not put the unit convention in the generic prompt; it belongs ONLY in the
  fixture `CLAUDE.md`, or TR3 has no measurable delta. Keep the theme (percentages) distinct from the cross-file
  bug's theme (dict keys) so the two never blur in scoring.
- **VALIDATE**: `$PY -m py_compile fixtures/sample-repo/src/pricing.py`

### CREATE `fixtures/sample-repo/src/ingest.py` + `src/summary.py` (cross-file bug — Phase-3 target)
- **IMPLEMENT**: A cross-file data-flow bug that single-file review is *expected to miss*: `ingest.py` builds
  records with key `"user_id"` (`def to_record(u): return {"user_id": u.id, ...}`); `summary.py` consumes them
  reading `rec["userId"]` (`def summarize(records): return [r["userId"] for r in records]`) → runtime
  `KeyError`. Each file **in isolation looks fine**; only cross-file reasoning reveals the key mismatch. Header
  comments state "SEEDED: cross-file key mismatch; ground-truth case `cross-file-key-mismatch`
  (requires_integration_pass=true) — Phase-2 single-pass is EXPECTED to miss this; Phase-3 integration pass
  catches it."
- **PATTERN**: intent-comment convention.
- **GOTCHA**: Do not make the mismatch obvious within either single file (no comment like "# matches summary.py")
  — the whole point is it needs the integration pass. Keep the two key spellings plausibly independent.
- **VALIDATE**: `$PY -m py_compile fixtures/sample-repo/src/ingest.py fixtures/sample-repo/src/summary.py`

### CREATE `fixtures/sample-repo/pr.diff` and `pr-02.diff`
- **IMPLEMENT**:
  - `pr.diff` — a valid unified diff (`--- a/… / +++ b/… / @@` hunk headers) that ADDS all four src files above
    (or their buggy lines) as one "PR". This is what `make metrics` reviews. Ensure the seeded lines land on
    hunk line numbers that match `ground_truth.json`.
  - `pr-02.diff` — a SECOND, smaller PR that RE-INTRODUCES the **None-deref issue class** in a *different* file
    (e.g. `src/accounts.py`, same shape) — the input for the severity-consistency gate (same class must get the
    same label as in `pr.diff`).
- **PATTERN**: Phase-1 `fixtures/pr-01/sample.diff` diff format.
- **GOTCHA**: Diffs contain `{`/`}` — prompt composition uses `.replace("{diff}", …)` (P1 decision), never
  `str.format`. Line numbers come from the **new-file** hunk numbering.
- **VALIDATE**: `grep -qE '^@@' fixtures/sample-repo/pr.diff && grep -qE '^@@' fixtures/sample-repo/pr-02.diff && echo OK`

### CREATE `fixtures/sample-repo/ground_truth.json` (the answer key)
- **IMPLEMENT**: The machine-readable ground truth the scorer compares against:
  ```json
  {
    "diff": "pr.diff",
    "cases": [
      {"id": "none-deref", "file": "src/orders.py", "line": 12, "should_flag": true,
       "expected_category": "correctness", "expected_severity": "high", "requires_integration_pass": false},
      {"id": "pct-as-fraction", "file": "src/pricing.py", "line": 9, "should_flag": false,
       "note": "correct under CLAUDE.md unit convention; the TR3 lever + idiomatic case"},
      {"id": "cross-file-key-mismatch", "file": "src/summary.py", "line": 8, "should_flag": true,
       "expected_severity": "critical", "requires_integration_pass": true,
       "note": "Phase-2 single-pass expected to MISS; Phase-3 integration target"}
    ]
  }
  ```
  Fill `line` with the ACTUAL new-file line from `pr.diff`. Add a matching `none-deref` case for `pr-02.diff` in
  a separate top-level key (e.g. `"pr02_cases"`), or a second manifest — whichever the scorer reads (keep it
  simple: the scorer takes a `cases` list; drive `pr-02` with its own small inline list in the test).
- **GOTCHA**: This file is the eval artifact — `workspace.stage_workspace` MUST exclude it. It is NEVER passed
  to the model. Keep `should_flag=false` cases explicit; every finding NOT matching a `should_flag=true` case is
  a false positive.
- **VALIDATE**: `$PY -c "import json; d=json.load(open('fixtures/sample-repo/ground_truth.json')); print(len(d['cases']), [c['id'] for c in d['cases']])"`
  → expect `3 ['none-deref', 'pct-as-fraction', 'cross-file-key-mismatch']`

### CREATE `fixtures/sample-repo/CLAUDE.md` (TR3 runtime context — role #2, NOT dev guidance)
- **IMPLEMENT**: The reviewed project's memory the bot loads at runtime. Contents:
  - **Project conventions** that change review behavior — most importantly the unit rule that exonerates
    `pricing.py`: "All rates and percentages in this codebase are stored as fractions in `[0.0, 1.0]`. Code that
    multiplies by `(1 - rate)` is correct; dividing a rate by 100 would be the bug."
  - **Review criteria** pointer (mirrors what the enriched prompt says, but as project policy): flag only
    genuine defects; respect documented conventions.
  - **Severity rubric** reference (the project's severity policy — reinforces TR5).
- **PATTERN**: PRD §"the reviewed project's CLAUDE.md carries the review criteria for TR3"; the two-CLAUDE.md
  rule in THIS repo's `CLAUDE.md`.
- **GOTCHA**: This is the ONLY place the unit convention lives — if you also put it in the generic prompt, the
  TR3 present-vs-absent delta vanishes. Keep it project-specific.
- **VALIDATE**: `test -f fixtures/sample-repo/CLAUDE.md && grep -qi 'fraction' fixtures/sample-repo/CLAUDE.md && echo OK`

### CREATE `.claude/commands/review/review-diff.baseline.md` (the "before" arm)
- **IMPLEMENT**: A **verbatim snapshot of the Phase-1 minimal `review-diff.md`** (the pre-TR4/TR5 prompt). This
  is the baseline the metric measures against. Copy it before enriching the real prompt.
- **GOTCHA**: If Phase 1's `review-diff.md` has already been informally improved, snapshot the genuinely minimal
  version (just "review this diff, report genuine issues via structured output; line = new-file line") — the
  baseline must be honestly weaker than the enriched prompt or the before/after number is meaningless.
- **VALIDATE**: `test -f .claude/commands/review/review-diff.baseline.md && grep -q '{diff}' .claude/commands/review/review-diff.baseline.md && echo OK`

### UPDATE `.claude/commands/review/review-diff.md` (ENRICH — TR4 + TR5)
- **IMPLEMENT**: Keep the `{diff}` placeholder and the "line = new-file line" note; ADD:
  - **Explicit FLAG criteria** (concrete, not "be conservative"): flag only when — a comment/docstring's claimed
    behavior contradicts the code; a realistic input causes a wrong return/raise (None-deref, off-by-one,
    KeyError, unhandled error path); a security-sensitive op is unsafe; a resource leak is demonstrable.
  - **Explicit DON'T-FLAG criteria**: style/formatting; naming; idiomatic-but-unusual patterns that are correct;
    anything the **project's CLAUDE.md declares intentional/conventional**; hypotheticals with no concrete
    trigger; test code unless it asserts wrong behavior.
  - **Few-shot pairs (TR4)**: 2–3 contrasting mini-examples, each `Code → Verdict`: (a) an *acceptable idiom* →
    "no finding" with the reason, vs (b) a *genuine bug of the same surface shape* → "finding" with
    severity+pattern. Make the pairs teach the discrimination, not memorize the fixture.
  - **Severity rubric (TR5)**: `critical / high / medium / low`, EACH with a one-line definition **and a
    concrete code example** (e.g. critical = "data corruption / RCE / auth bypass — e.g. `eval(user_input)`";
    high = "crash on realistic input — e.g. None-deref on a lookup miss"; medium = "wrong result in an edge
    case"; low = "minor correctness risk / missing guard, no crash").
  - **Field guidance**: `detected_pattern` = short kebab slug from a small controlled set (align with
    `PATTERN_SEVERITY` keys so the override engages); `category` = one of `correctness|security|performance|
    maintainability`.
- **PATTERN**: PRD Feature "Precision Prompt" (§7, lines 214–218); `.claude/commands/*.md` frontmatter style
  (`---\ndescription: …\n---`) from `.claude/commands/core_piv_loop/plan-feature.md:1–4`.
- **GOTCHA**: The prompt carries **generic** discrimination (idiom vs bug in general); **project-specific**
  conventions live in the fixture `CLAUDE.md` (TR3 separation). Prompt text is NEVER asserted on in tests
  (validation is structural) — you may refine wording freely to hit the fixture outcomes.
- **VALIDATE**: `grep -q '{diff}' .claude/commands/review/review-diff.md && grep -qiE 'critical|severity' .claude/commands/review/review-diff.md && echo OK`

### UPDATE `src/review/runner.py` (add the `cwd` lever — TR3)
- **IMPLEMENT**: Add `cwd: str | None = None` to `invoke_claude(...)` and pass `cwd=cwd` to `subprocess.run`.
  Nothing else changes (still `capture_output=True, text=True, timeout=timeout_s`, stdout/stderr separate). This
  single param is what lets the run auto-load the staged workspace's `CLAUDE.md`.
- **PATTERN**: the Phase-1 `runner.invoke_claude` body (unchanged except the new kwarg).
- **IMPORTS**: none new.
- **GOTCHA**: keep the kwarg **optional** with a `None` default so every existing Phase-1 call site and test
  keeps working. `subprocess.run(cwd=None)` = current dir (Phase-1 behavior preserved).
- **VALIDATE**: `PYTHONPATH=src/review $PY -c "import inspect,runner; print('cwd' in inspect.signature(runner.invoke_claude).parameters)"`
  → expect `True`

### CREATE `src/review/metrics.py` (pure scorer + thin live driver)
- **IMPLEMENT**: Two clearly separated layers:
  - **Pure scorer (offline, stdlib-only, deterministic, never raises):**
    - `@dataclass MetricsResult` (fields per the "Result dataclass" pattern above).
    - `match(finding, case, tolerance) -> bool` — `finding.location.file` endswith/equals `case["file"]` AND
      `abs(finding.location.line - case["line"]) <= tolerance`. (Normalize path separators; the model may report
      `src/orders.py` vs `orders.py` — match on suffix.)
    - `score(findings: list[Finding], cases: list[dict], *, tolerance, single_pass=True) -> MetricsResult`:
      - eligible cases = those with `requires_integration_pass` False when `single_pass=True` (the cross-file
        case is excluded from P2 recall and REPORTED SEPARATELY as a known gap — keeps the P2 number honest and
        sets up P3).
      - For each `should_flag=true` eligible case: TP if any finding matches, else FN.
      - FP = findings matching a `should_flag=false` case OR matching NO eligible case at all (spurious).
      - `precision = tp/(tp+fp)` (1.0 if no findings & no positives), `recall = tp/(tp+fn)`, `f1` harmonic mean
        (0.0 when precision+recall == 0). Guard all divisions.
    - `format_report(baseline: MetricsResult, enriched: MetricsResult) -> str` — a before/after table string.
  - **Live driver (integration — needs CLI+key):**
    - `run_variant(prompt_path, model, *, include_claude_md=True) -> list[Finding]`: read+frontmatter-strip the
      prompt, `.replace("{diff}", <pr.diff text>)`, `workspace.staged(FIXTURE_REPO, include_claude_md)` →
      `runner.invoke_claude(prompt, schema.as_json_string(), model, CLAUDE_TIMEOUT_S, cwd=staged_dir)` →
      `parse.parse_result(stdout)` → `severity.apply_canonical_severity(findings)`.
    - `run_metrics() -> dict`: run baseline vs enriched variants (both with CLAUDE.md present), `score` each,
      write `data/metrics/{baseline,enriched}.json`, return + print `format_report`. This is `make metrics`.
    - `run_tr3_demo() -> dict`: run the ENRICHED prompt twice — CLAUDE.md present vs absent — and report whether
      the `pct-as-fraction` case was flagged in each (expected: absent→flagged FP, present→not). This is
      `make tr3-demo`.
- **PATTERN**: pure-core/live-driver split mirrors `coverage_eval.py` (pure) + `test_phase3_coverage_live.py`
  (live) separation; `MetricsResult` mirrors `CoverageResult` (lines 51–57).
- **IMPORTS**: pure layer: `json`, `dataclasses`, `from parse import Finding`. Driver: `config`, `schema`,
  `runner`, `parse`, `severity`, `workspace` (flat imports).
- **GOTCHA**: Keep `score`/`match`/`format_report` free of `subprocess`/`runner` imports at module top so
  `test_metrics.py` runs offline. Import the driver deps at the top is fine (they don't call the CLI on import),
  but the SCORER functions must not touch the CLI. Suffix-match file paths (staged/relative vs ground-truth
  relative).
- **VALIDATE**: `PYTHONPATH=src/review $PY -c "from parse import Finding,Location; import metrics; f=[Finding(Location('src/orders.py',12),'None deref','high','x','none-deref','correctness')]; cases=[{'id':'none-deref','file':'src/orders.py','line':12,'should_flag':True,'requires_integration_pass':False},{'id':'pct-as-fraction','file':'src/pricing.py','line':9,'should_flag':False}]; r=metrics.score(f,cases,tolerance=3); print(r.tp,r.fp,r.fn,r.precision,r.recall)"`
  → expect `1 0 0 1.0 1.0`

### UPDATE `src/review/cli.py` (prompt-variant selection + canonical severity)
- **IMPLEMENT**: ADD optional args `--prompt {enriched,baseline}` (default `enriched`; maps to
  `config.ENRICHED_PROMPT` / `config.BASELINE_PROMPT`) and `--repo <path>` (optional; when given, stage that
  repo's `CLAUDE.md` via `workspace` and pass `cwd`). In the flow, after `parse.parse_result` and before
  `post.emit`, apply `severity.apply_canonical_severity(findings)` and `severity.sort_by_severity(...)`. Keep
  the Phase-1 `--diff`/`--model` behavior and all exit-code/timeout handling intact.
- **PATTERN**: Phase-1 `cli.py` flow; add args in the same argparse block.
- **IMPORTS**: `import severity, workspace` (flat); reuse existing.
- **GOTCHA**: Default behavior (no `--repo`) must stay identical to Phase 1 so P1 tests/manual demo still pass.
  Only stage a workspace when `--repo` is provided (or when metrics drives it). Don't break `make ci-review
  PR=fixtures/pr-01/sample.diff`.
- **VALIDATE**: `PYTHONPATH=src/review $PY -m cli --help` (shows `--prompt`, `--repo`; exit 0)

### UPDATE `Makefile` (add `metrics` + `tr3-demo`)
- **IMPLEMENT**: ADD targets (tabs, not spaces):
  - `metrics:` → `PYTHONPATH=src/review $(PY) -c "import metrics; metrics.run_metrics()"`
  - `tr3-demo:` → `PYTHONPATH=src/review $(PY) -c "import metrics; metrics.run_tr3_demo()"`
  - add both to `.PHONY`. Leave the Phase-3 `test-gen` target as the existing stub.
- **PATTERN**: the Phase-1 `Makefile` (`PY=../../.venv/bin/python`, `PYTHONPATH=src/review`, `.PHONY`).
- **GOTCHA**: `metrics`/`tr3-demo` make LIVE model calls (cost + need CLI/key) — they are effectively
  integration targets; note that in a comment. They are NOT run by `make test`.
- **VALIDATE**: `make -n metrics && make -n tr3-demo` (dry-run prints the commands)

### CREATE `tests/test_severity.py` (OFFLINE)
- **IMPLEMENT**: (1) `normalize_severity` maps aliases (`"BLOCKER"→"critical"`, `"warn"→"medium"`,
  unknown→`"medium"`); (2) `canonical_severity` overrides a known pattern regardless of the model's label
  (a `none-deref` finding labeled `"low"` → `"high"`); (3) an UNKNOWN pattern falls back to
  `normalize_severity(model_label)`; (4) `apply_canonical_severity` returns new objects (no mutation) and is
  idempotent; (5) `sort_by_severity` orders critical→low. `@pytest.mark.parametrize` the alias table.
- **PATTERN**: `../multi-agent-research-agent/tests/test_coverage.py` (parametrize + constant assertions).
- **VALIDATE**: `$PY -m pytest tests/test_severity.py -q`

### CREATE `tests/test_metrics.py` (OFFLINE)
- **IMPLEMENT**: With hand-authored `Finding` lists + a `cases` list (no CLI): (1) perfect findings →
  precision=recall=1.0; (2) flagging the `should_flag=false` `pct-as-fraction` case → an FP, precision drops;
  (3) missing the `none-deref` case → an FN, recall drops; (4) a spurious finding on an unlabeled line → FP;
  (5) the `requires_integration_pass` case is EXCLUDED from single-pass recall (not counted FN) and surfaced as
  a known gap; (6) line-tolerance matching (finding at line 14 matches a case at line 12 with tolerance 3);
  (7) suffix path matching (`orders.py` matches `src/orders.py`); (8) `format_report` contains both numbers.
- **PATTERN**: `test_coverage.py` fixture-string + assertion style.
- **GOTCHA**: **No `claude` call** — import only the pure scorer functions. This is the ground-truth check that
  the metric itself is correct before trusting any live number.
- **VALIDATE**: `$PY -m pytest tests/test_metrics.py -q`

### CREATE `tests/test_workspace.py` (OFFLINE)
- **IMPLEMENT**: (1) `stage_workspace(FIXTURE_REPO, include_claude_md=True)` → staged dir CONTAINS `CLAUDE.md`
  and does NOT contain `ground_truth.json` or any `*.diff`; (2) `include_claude_md=False` → no `CLAUDE.md`;
  (3) staged dir is under `tempfile.gettempdir()` (outside the repo); (4) `cleanup_workspace` removes it and
  refuses a non-temp path (footgun guard). Use the `staged` context manager and assert cleanup on exit.
- **PATTERN**: stdlib `tempfile`/`os` assertions.
- **GOTCHA**: this test is the guard that the **answer key never leaks** to the model — treat a failure as a
  correctness bug, not a flake.
- **VALIDATE**: `$PY -m pytest tests/test_workspace.py -q`

### CREATE `tests/test_precision_live.py` [integration] (the acceptance demos)
- **IMPLEMENT**: `@pytest.mark.integration` + `skipif(not claude_runnable())`, `model=config.BASELINE_MODEL`
  (haiku, cost cap). Tests:
  1. **Real bug flagged, idiomatic not flagged (enriched + CLAUDE.md present):** run enriched variant; assert a
     finding matches the `none-deref` case AND NO finding matches the `pct-as-fraction` case.
  2. **Precision improves before→after (TR4/TR5):** run baseline and enriched; assert
     `enriched.precision >= baseline.precision` (and record both to `data/metrics/`). Assert on the *direction*
     of the number, never on wording.
  3. **TR3 behavior change:** enriched prompt, CLAUDE.md present vs absent; assert the `pct-as-fraction` case is
     flagged in the ABSENT run and NOT flagged in the PRESENT run (the demonstrable delta).
  4. **Severity consistency (TR5):** review `pr.diff` and `pr-02.diff`; assert the `none-deref`-class finding
     has the SAME severity label in both (guaranteed by `apply_canonical_severity`).
  5. **Cross-file is missed single-pass:** assert the `cross-file-key-mismatch` case is NOT flagged by the
     single-pass enriched run (documents the Phase-3 gap — an *expected* miss, not a failure).
- **PATTERN**: `test_phase3_coverage_live.py` integration gating (`pytestmark = [integration, skipif(...)]`).
- **GOTCHA**: These calls cost money and are non-deterministic — assert on **structure/direction/outcomes**
  (matched cases, precision inequality, label equality), NEVER on the model's prose. Allow a tiny retry or
  tolerance if a single run is flaky, but prefer robust fixture design over loosening asserts. If test #1/#3
  don't reproduce cleanly, **iterate the fixture** (`pricing.py` + `CLAUDE.md` wording) until the delta is real
  — the fixture is ground truth and calibrating it is expected precision work.
- **VALIDATE**: `export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-); $PY -m pytest -m integration tests/test_precision_live.py -q`

### UPDATE `_tasks/todo.md`
- **IMPLEMENT**: Add a "Phase 2 — Precision" checklist mirroring these tasks; mark complete as you go; append a
  review section (what worked / what didn't / the recorded before-vs-after precision number).
- **VALIDATE**: `test -f _tasks/todo.md`

---

## TESTING STRATEGY

### Unit Tests (offline, default `-m "not integration"`)
- **severity** (`test_severity.py`): normalization aliases; canonical pattern override (the TR5 determinism
  lever); no-mutation/idempotency; ordering.
- **metrics scorer** (`test_metrics.py`): TP/FP/FN and precision/recall/F1 over hand-authored findings vs a
  `cases` list; integration-pass exclusion; line-tolerance + suffix path matching; report formatting. **This is
  the ground-truth check that the metric is correct before any live number is trusted.**
- **workspace** (`test_workspace.py`): staging includes `CLAUDE.md`, **excludes `ground_truth.json`/`*.diff`**,
  lives under `$TMPDIR`, cleanup refuses non-temp paths.
- All: `capsys`/plain assertions; **never assert on model wording** (PRD principle 5). No CLI/network.

### Integration Tests (`-m integration`, gated on `claude_runnable()`, haiku tier)
- **precision-live** (`test_precision_live.py`): the five acceptance demos — real-bug-flagged/idiom-not-flagged,
  precision before→after, TR3 present-vs-absent, severity consistency across two PRs, cross-file-missed-
  single-pass. Assert on structure/direction/outcomes only.

### Edge Cases (must be covered)
- A `should_flag=false` case that gets flagged → counted as FP (precision drops) — the core failure mode.
- Empty findings on the enriched run of a clean sub-diff → precision defined (1.0), no crash.
- Finding line off by ≤ tolerance from ground truth → still a match; off by > tolerance → miss.
- Finding path reported as bare filename vs `src/…` → suffix match still works.
- `requires_integration_pass` case excluded from P2 recall (not a false FN) and reported as a known gap.
- CLAUDE.md-absent run leaks NO project memory (staged under `$TMPDIR`); present-run loads exactly the fixture's.

---

## VALIDATION COMMANDS

Run from the project root (`.../projects/claude-code-ci-review-bot`). `PY=../../.venv/bin/python`.

### Level 1: Syntax & Style
```bash
../../.venv/bin/python -m py_compile src/review/*.py tests/*.py fixtures/sample-repo/src/*.py
# (no ruff/black in the shared venv — py_compile is the syntax gate)
```

### Level 2: Unit Tests (offline — MUST pass with zero network/CLI)
```bash
../../.venv/bin/python -m pytest -m "not integration" -q
```

### Level 3: Integration Tests (needs `claude` CLI + ANTHROPIC_API_KEY; haiku cost)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
../../.venv/bin/python -m pytest -m integration tests/test_precision_live.py -q
```

### Level 4: Manual Validation (the headline deliverable)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
make metrics     # prints the before-vs-after precision/recall table; writes data/metrics/*.json
make tr3-demo    # prints the CLAUDE.md present-vs-absent behavior change on the pct-as-fraction case
```
EXPECT: enriched precision ≥ baseline precision; the `pct-as-fraction` case flagged with CLAUDE.md ABSENT and
NOT flagged with it PRESENT.

### Level 5: Additional Validation (optional)
```bash
# Prove the review still runs non-interactively end-to-end on the fixture PR.
make ci-review PR=fixtures/sample-repo/pr.diff --repo fixtures/sample-repo < /dev/null; echo "exit: $?"
```

---

## ACCEPTANCE CRITERIA

- [ ] On the fixture, the **genuine bug (`none-deref`) IS flagged** and the **convention-dependent
      (`pct-as-fraction`) is NOT flagged** (enriched prompt + CLAUDE.md present).
- [ ] A **precision/recall number is reported before vs. after TR4/TR5** (baseline vs enriched), with
      `enriched.precision >= baseline.precision`, persisted to `data/metrics/`.
- [ ] **TR3 behavior change demonstrated**: the `pct-as-fraction` case is flagged with the fixture CLAUDE.md
      ABSENT and not flagged with it PRESENT (all else equal).
- [ ] **Severity is identical for the same issue class across two PRs** (`pr.diff` vs `pr-02.diff`), guaranteed
      by `apply_canonical_severity`.
- [ ] The **cross-file bug is NOT caught by the single-pass** review (documented expected gap for Phase 3).
- [ ] Review criteria/conventions reach the run **via the fixture's CLAUDE.md and the versioned prompt**, never
      hand-pasted into `-p`; the bot-dev CLAUDE.md does **not** leak (staged workspace under `$TMPDIR`).
- [ ] The **answer key never reaches the model** (`test_workspace.py` proves `ground_truth.json`/`*.diff` are
      excluded from staging).
- [ ] Offline unit suite (`-m "not integration"`) passes with **no network/CLI**; integration suite passes when
      the CLI is available (skips cleanly otherwise).
- [ ] No `claude-agent-sdk` / `anthropic` / `gh` imports (CLI-as-agent; posting is Phase 4).
- [ ] Phase-1 behavior preserved: `make ci-review PR=fixtures/pr-01/sample.diff` still works; P1 tests green.

---

## COMPLETION CHECKLIST
- [ ] Phase 1 verified present & green BEFORE starting; interfaces reconciled with the real code.
- [ ] All tasks completed in order; each task's `VALIDATE` passed immediately.
- [ ] Level 1–4 validation commands executed successfully; before/after number recorded in `_tasks/todo.md`.
- [ ] Offline unit suite green; integration suite green (or cleanly skipped).
- [ ] No linting/type errors (py_compile clean).
- [ ] `make metrics` + `make tr3-demo` produce the two demonstrable deltas.
- [ ] `_tasks/todo.md` updated with a completion review (incl. the headline precision number).

---

## NOTES

**Decisions made during planning (with rationale):**
1. **Staged temp workspace outside the monorepo is the TR3 mechanism** (not `cwd=fixtures/sample-repo`
   directly). Verified: `claude -p` walks UP the tree loading every ancestor `CLAUDE.md`, so an in-repo cwd
   would leak the bot-dev CLAUDE.md + `~/.claude` into the review (PRD Risk #3). Staging under `$TMPDIR` makes
   the fixture's own CLAUDE.md the ONLY project-memory variable — a clean, controlled A/B. Both TR3 arms run
   non-`--bare` (identical except the file); `--bare` is a documented fallback only, since it also strips
   hooks/plugins/user memory and would confound the delta.
2. **Two distinct A/B experiments, not one.** (a) baseline vs enriched *prompt* with CLAUDE.md constant →
   the TR4/TR5 precision number; (b) CLAUDE.md present vs absent with the enriched prompt constant → the TR3
   behavior change. Conflating them would make neither number attributable.
3. **`severity.py` carries a canonical `PATTERN_SEVERITY` override, layered on the prompt rubric.** The TR5
   *primary* lever is the rubric-with-examples (shapes what the model emits); the override is the *backstop*
   that makes "identical severity across PRs" **deterministic** rather than dependent on model consistency —
   which is what the acceptance gate actually requires. Mirrors the pure/deterministic sibling style so it's
   unit-testable offline.
4. **The metric scorer is pure and unit-tested BEFORE any live number is trusted.** A wrong scorer would make
   the headline trust metric a lie; `test_metrics.py` is the ground-truth check on the ground-truth harness.
5. **Cross-file case is seeded now but excluded from P2 single-pass recall** (reported as a known gap). Keeps
   the Phase-2 number honest (recall isn't artificially depressed by a case the design can't yet catch) and
   sets up the Phase-3 integration pass to flip it to a TP.
6. **Fixture themes kept distinct** (None-deref / percentage-unit convention / dict-key mismatch) so the three
   cases never blur during scoring or prompt calibration.
7. **Baseline model = haiku for metrics/integration** (cost cap, mirrors sibling `CLASSIFIER_MODEL`);
   `REVIEW_MODEL` (sonnet) stays the production default. Same tier across both A/B arms so the model is not a
   confound.

**Prerequisites & environment gotchas:**
- **Phase 1 must be executed first** — this plan has no spine to build on otherwise (first task enforces it).
- Shared venv Python 3.10 at `../../.venv`; `jsonschema`/`pytest`/`python-dotenv` already installed → no new
  deps.
- `gh` auth is currently broken and irrelevant here (posting is Phase 4).
- No `ruff`/`black` → Level 1 is `py_compile` only.
- Prompt calibration is empirical: if the TR3/precision deltas don't reproduce, iterate the fixture
  (`pricing.py` + fixture `CLAUDE.md` wording) — the fixture is ground truth and tuning it is the work, not a
  workaround.

**Out of scope for Phase 2 (do not build):** multi-pass / independent instance (TR6/TR7 — P3), dedupe / prior-
findings context (TR8 — P3), test generation (FR2 — P3), `detected_pattern` dismissal tracking + category
quarantine (TR9/FR4 — P4), real `gh --post` (P4).
