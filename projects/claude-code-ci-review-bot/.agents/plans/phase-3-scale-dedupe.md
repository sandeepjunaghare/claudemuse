# Feature: Phase 3a — Scale + Dedupe (TR6 / TR7 / TR8 / FR3)

The following plan should be complete, but it's important that you **validate documentation, codebase patterns,
and task sanity before you start implementing**. Pay special attention to the naming of existing utils, types,
and models from Phases 1–2 — **import from the right files** (`from parse import Finding, Location`), and do
**not** reshape the Phase-1/2 contract (`FINDINGS_SCHEMA`, `Finding`, `invoke_claude`, `parse_result`).

> **PREREQUISITE — verify first.** Phases 1 and 2 are implemented and committed (branch
> `feat/ci-review-bot-scaffold`, offline suite **53 passed**). This plan builds directly on that spine. The very
> first task re-verifies the interfaces below against the **actual code on disk** and adapts if anything drifted
> — the real code wins over this plan.

> **Ground-truth already established (do not re-derive):**
> - Every `claude -p` invocation is a **separate OS process** with **no shared conversation/reasoning context**.
>   That is the entire mechanism behind **TR7 (independent review instance)** in this architecture — it is
>   satisfied *by construction* (a process boundary), not by a prompt instruction and not by `--continue` /
>   `--resume` (which we never use). The multipass orchestrator makes N+1 independent `invoke_claude` calls.
> - `claude -p` auto-loads `CLAUDE.md` from `cwd` + ancestors. Phase 2 already solved the isolation via
>   `workspace.staged(...)` under `$TMPDIR`. **Reuse it** — all multipass passes share ONE staged workspace
>   (separate processes reading the same `CLAUDE.md` are still independent; TR7 is about reasoning context, not
>   the filesystem). Do not re-solve isolation.
> - Phase-2 empirical finding (recorded in `_tasks/todo.md`): a **whole-diff** single pass has cross-file
>   visibility and *can opportunistically* catch the seeded cross-file bug. **Per-file *isolation* is what
>   genuinely cannot** — each file alone looks correct. That is exactly the TR6 lever this phase exploits:
>   per-file passes MISS the cross-file bug; the integration pass CATCHES it.

> **SCOPE — Phase 3a only.** This plan covers **TR6** (multi-pass), **TR7** (independent instance), **TR8/FR3**
> (duplicate suppression across re-runs). **Test generation (FR2/FR3-testgen) is DEFERRED to a separate Phase-3b
> plan** (`.agents/plans/phase-3b-testgen.md`, not yet written) — it needs its own output schema, versioned
> command, and fixture, and is cleanly separable. **`detected_pattern` dismissal tracking + category quarantine
> (TR9/FR4) and real `gh --post` remain Phase 4.** Do not build any of those here.

---

## Feature Description

Phase 3a turns the Phase-2 *single-pass, precise* reviewer into one that **scales to large PRs without attention
dilution** and **stops spamming duplicate comments across re-runs**. It adds the three things the PRD groups as
"Scale + Dedupe":

1. **Multi-pass review (TR6).** Split the PR diff into **per-file sub-diffs**, review each in its own isolated
   `claude -p` pass, then run **one separate cross-file integration pass** over the whole diff. Merge and dedupe
   the results. Per-file passes keep each review focused (no attention dilution on a large PR); the integration
   pass is the *only* pass that can see cross-module data-flow, so it is the one that catches the seeded
   `cross-file-key-mismatch` bug that per-file isolation provably misses.
2. **Independent review instance (TR7).** Each pass is a **fresh `claude -p` process** with zero shared context.
   This is a structural property of the orchestrator (N+1 independent `invoke_claude` calls, never a session
   resume), not a prompt trick — and it is unit-testable offline by counting the calls.
3. **Duplicate suppression across re-runs (TR8 / FR3).** Two layers, mirroring the proven Phase-2
   severity two-layer pattern:
   - **Structural backstop (deterministic, offline-testable):** a pure `dedupe.py` that collapses duplicate
     findings within a run (per-file + integration overlap) and, on a re-run, **suppresses findings already
     reported in a prior run** (matched by file + `detected_pattern` + line-within-tolerance). This is the
     deterministic guarantee behind "a second commit produces zero duplicate comments."
   - **Prompt-context layer (semantic, handles line drift):** on a re-run, prior findings are fed into the
     review prompt with an instruction to report only **new or still-unresolved** issues (FR3). This catches
     duplicates the structural key would miss when line numbers drift across commits.
   Prior findings persist in `data/prior_findings/{pr_id}.json` (a small `store.py`).

Phase 3a is deliberately **still emit-only** (no `gh` posting) and does **not** add test-gen or quarantine.

## User Story

As a **wary senior engineer reviewing a large, multi-file PR that I re-push fixes to**,
I want the bot to **review each file with full attention, catch bugs that only appear across files, and never
re-comment an issue it already flagged on my previous push**,
So that **the review stays trustworthy and readable on big PRs and across commits** — instead of diluting its
attention across a huge diff or burying me in duplicate comments every time I push.

## Problem Statement

Phase 2 proved the bot is *precise on a small single-pass diff*, but two trust-killers remain (PRD §1, FR3):
1. **Large PRs dilute attention** — one prompt reviewing a 40-file diff reasons shallowly about each file, and a
   single pass either misses cross-module contract breaks or (worse) emits contradictory findings across files.
2. **Re-runs spam duplicates** — today, re-running on a second commit re-emits every still-unresolved finding as
   a *new* comment. On a real PR that buries the reviewer and gets the bot muted — the exact failure mode the
   whole project exists to prevent.

There is currently **no diff-splitting**, **no integration pass**, **no dedupe**, and **no prior-findings
memory**. The cross-file bug is seeded and sitting as a *known gap* in the Phase-2 scorer, waiting for this
phase's integration pass to flip it from an excluded gap to a scored true positive.

## Solution Statement

Add a **pure diff splitter + a live multipass orchestrator** (`multipass.py`): per-file isolated passes (each a
fresh `claude -p` = TR7) + one whole-diff integration pass using a new versioned `review-integration.md` prompt
focused on cross-module/data-flow/contract issues (TR6). Merge all findings through a **pure, deterministic
`dedupe.py`** that collapses within-run duplicates and suppresses prior-run findings (TR8/FR3), with a small
`store.py` persisting prior findings per PR. Wire it into `cli.py` behind a `--mode {single,multi}` flag and an
opt-in `--pr-id` (which enables dedupe), keeping every Phase-1/2 default behavior byte-for-byte intact. All
orchestration logic is unit-tested **offline** by monkeypatching `runner.invoke_claude` to return canned CLI
output (proving the fan-out shape, the isolation, and the merge/dedupe without spending a token); the real-model
behavior (per-file misses cross-file, integration catches it, re-run suppresses) is `integration`-marked on the
cheap haiku tier. The Phase-2 scorer already supports `single_pass=False` — Phase 3a feeds it the multipass
result so the cross-file case scores as a **TP**, not a known gap.

## Feature Metadata

**Feature Type**: Enhancement (adds scale + dedupe onto the Phase-2 precise reviewer)
**Estimated Complexity**: Medium (low algorithmic complexity; the care is in diff-splitting correctness,
offline-testable orchestration via monkeypatch, and honest dedupe semantics)
**Primary Systems Affected**: `src/review/` (new `multipass.py`, `dedupe.py`, `store.py`; modify `cli.py`,
`config.py`), `.claude/commands/review/` (new `review-integration.md`), `data/prior_findings/` (new),
`tests/` (new unit + integration), `Makefile` (new targets)
**Dependencies**: none new — `jsonschema`, `python-dotenv`, `pytest` already in the shared venv (`../../.venv`).
Claude Code CLI on PATH is the agent under test.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**Phase-1/2 code in THIS repo (read the ACTUAL files; line numbers current as of planning):**
- `src/review/runner.py` (lines 28–74) — `invoke_claude(prompt, schema_json, model, timeout_s, cwd=None) ->
  RunResult(stdout, stderr, returncode)`. Why: multipass calls this once per pass. **The signature is already
  final — do not change it.** `cwd` is the TR3 lever (Phase 2). Monkeypatch this in offline tests.
- `src/review/parse.py` (lines 24–52 `Location`/`Finding`/`ParsedReview`; 54–128 `parse_result`). Why:
  `dedupe.py`, `store.py`, `multipass.py` all operate on `Finding` objects — **import them, never redefine**.
  `Finding` fields (order): `location(Location(file,line))`, `issue`, `severity`, `suggested_fix`,
  `detected_pattern`, `category`. `parse_result(stdout) -> ParsedReview` handles the CLI event stream + error
  envelope; multipass reuses it per pass.
- `src/review/schema.py` (lines 20–58 `FINDINGS_SCHEMA`, 61–63 `as_json_string`). Why: same schema for every
  pass (per-file and integration). **Phase 3a does NOT change the schema.**
- `src/review/severity.py` (lines 88–107 `canonical_severity`/`apply_canonical_severity`, 110–119
  `sort_by_severity`, 56–65 `PATTERN_SEVERITY`). Why: multipass applies canonical severity to the merged
  findings *before* dedupe compares them — this is what makes "no contradictory findings" structurally true
  (same `detected_pattern` → same severity, so two reports of one issue can't disagree). `cross-file-key-mismatch`
  is already mapped to `critical` (line 60).
- `src/review/metrics.py` (lines 49–54 `_same_file`, 57–73 `match`, 76–145 `score` incl. `single_pass` +
  `known_gaps`, 188–222 `run_variant`, 254–277 `run_metrics`, 280–326 `run_tr3_demo`). Why: (1) `_same_file`
  is the **exact path-suffix normalization** `dedupe.py` must mirror; (2) `score(..., single_pass=False)` already
  turns the cross-file case into an eligible positive — the multipass integration test scores against it; (3)
  `run_variant` / `run_tr3_demo` are the **template** for the multipass live driver + demo (local imports inside
  the function, staged workspace, `apply_canonical_severity` before returning).
- `src/review/cli.py` (lines 25–45 frontmatter-strip + `_compose_prompt`; 48–144 `main` flow — argparse,
  `load_env`, staged `--repo` cwd via `contextlib.ExitStack`, invoke → parse → `is_error` → canonical severity →
  sort → `emit`). Why: you add `--mode`, `--pr-id`, and the dedupe branch **without disturbing** the exit-code/
  timeout handling or the default (single-pass, no-dedupe) path.
- `src/review/workspace.py` (lines 83–94 `staged` context manager; 36–63 `stage_workspace`). Why: reuse
  `workspace.staged(repo, include_claude_md)` for the multipass live driver — do not write new staging.
- `src/review/post.py` (lines 12–29 `format_comment`/`emit`). Why: unchanged; `cli.py` still calls `emit` last.
- `src/review/config.py` (lines 23 `PROJECT_ROOT`, 45–61 fixture/metrics constants, 61 `LINE_MATCH_TOLERANCE`).
  Why: you ADD `INTEGRATION_PROMPT`, `PRIOR_FINDINGS_DIR`, `DEDUPE_LINE_TOLERANCE` here. Reuse `PROJECT_ROOT`.
- `.claude/commands/review/review-diff.md` (whole file) — the enriched per-file prompt. Why: **reused as-is** as
  the per-file pass prompt (it is diff-agnostic — fed one file's sub-diff it reviews that file). You author a
  *sibling* `review-integration.md`, you do NOT modify this one.
- `fixtures/sample-repo/` — `pr.diff` (4 files incl. the cross-file producer `ingest.py` / consumer
  `summary.py`), `ground_truth.json` (the `cross-file-key-mismatch` case has `requires_integration_pass: true`
  and accepts EITHER end via `locations`), `CLAUDE.md` (the settings policy). Why: the ground-truth harness —
  unchanged; Phase 3a scores the multipass result against it with `single_pass=False`.
- `tests/conftest.py` (lines 15–27 `sys.path` + `claude_runnable()`; 30–65 fixtures incl. `sample_findings`,
  `ground_truth`). Why: reuse the gate + fixtures; extend with any new fixtures Phase 3a needs.
- `tests/test_metrics.py` (whole file) — the **offline unit-test shape** to mirror for `test_dedupe.py` /
  `test_multipass.py`: hand-authored `Finding` lists via a `_f(...)` helper, assertions on structure only.
- `tests/test_precision_live.py` (lines 21–27 `pytestmark`; 56–66, 129–156 patterns). Why: the `integration`
  gating + "assert on outcomes never prose" pattern to mirror for `test_multipass_live.py`.

**Sibling house-style references (mirror EXACTLY — verified during Phase 2 planning):**
- `../multi-agent-research-agent/src/coverage_eval.py` — the canonical template for a **pure, total,
  deterministic, stdlib-only, never-raises** module: use it for `dedupe.py` (module docstring stating the
  contract; string constants; `@dataclass` result structs). Same style Phase-2 `severity.py`/`metrics.py`
  already follow — match those two, which are the in-repo precedent now.
- `../multi-agent-research-agent/tests/test_coverage.py` — parametrized offline assertions on structure/
  constants. Mirror for `test_dedupe.py` / `test_store.py`.

### New Files to Create

```
claude-code-ci-review-bot/
├── .claude/commands/review/
│   └── review-integration.md          # NEW: cross-file / data-flow / contract-focused prompt (TR6 integration pass)
├── src/review/
│   ├── multipass.py                   # NEW: pure split_diff + live per-file/integration/multipass orchestrator (TR6/TR7)
│   ├── dedupe.py                      # NEW: pure within-run + cross-run dedupe (TR8/FR3)
│   └── store.py                       # NEW: persist/load prior findings per PR (TR8/FR3)
├── data/prior_findings/               # NEW: per-PR prior-findings store for dedupe
│   └── .gitkeep
└── tests/
    ├── test_multipass.py              # OFFLINE: split_diff + orchestration via monkeypatched invoke_claude (TR6/TR7)
    ├── test_dedupe.py                 # OFFLINE: within-run collapse + prior-run suppression + tolerance/suffix
    ├── test_store.py                  # OFFLINE: Finding round-trip save/load; missing pr_id → []
    └── test_multipass_live.py         # [integration] per-file misses cross-file; integration catches; re-run suppresses
```

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Claude Code Headless mode](https://code.claude.com/docs/en/headless) — `-p` / `--output-format json` /
  `--json-schema` reference. Why: unchanged from P1/P2; each multipass pass is one such call. Confirms `-p`
  starts a **fresh** non-interactive session (no state carried between invocations) — the TR7 basis.
- [Claude Code Memory / CLAUDE.md loading](https://code.claude.com/docs/en/memory) — Why: confirms the staged
  workspace (Phase 2) still governs which `CLAUDE.md` each pass loads; no change needed.
- No new external library docs — `difflib` is **not** used; diff *splitting* is a trivial string split on
  `diff --git ` boundaries (stdlib only, shown inline below). `tempfile`/`shutil`/`json` usage is stdlib.

### The TR6 architecture (the crux)

```
              pr.diff (4 files)
                    │
        split_diff  │  (pure, offline-testable)
        ┌───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼
   orders.py   settings.py  ingest.py   summary.py     ← PER-FILE passes (TR7: each a fresh claude -p)
   [none-deref] [not flagged] [clean]    [clean]           each sees ONLY its own sub-diff → CANNOT see
        │           │           │           │              the user_id/userId mismatch (isolation)
        └───────────┴─────┬─────┴───────────┘
                          │  merge
                          ▼
                    whole pr.diff  ───────────────────▶  INTEGRATION pass (TR7: another fresh claude -p)
                                                          review-integration.md, sees ALL files →
                                                          CATCHES cross-file-key-mismatch
                          │                                        │
                          └──────────────┬─────────────────────────┘
                                         ▼
                          apply_canonical_severity  (severity.py — no contradictions)
                                         ▼
                          dedupe(...)  (dedupe.py — collapse per-file/integration overlap)
                                         ▼
                          [none-deref (high), cross-file-key-mismatch (critical)]
                                         ▼
                    suppress_prior(...) on re-run  (dedupe.py + store.py — TR8/FR3)
```

**Why per-file passes provably miss the cross-file bug:** `ingest.py`'s sub-diff writes `"user_id"` with no
consumer in view → correct in isolation. `summary.py`'s sub-diff reads `rec["userId"]` → a plausibly-existing
key in isolation. Only a pass that sees BOTH can connect them. This is the honest TR6 demonstration Phase 2
couldn't make (its whole-diff pass had cross-file visibility and was recorded as a *known gap*).

### Patterns to Follow

**Naming (Python — snake_case):** functions/vars `snake_case`, dataclasses `PascalCase`, module constants
`UPPER_SNAKE`. String constants, not enums (repo precedent: `severity.SEVERITY_LEVELS`).

**Pure-module docstring + contract (mirror `severity.py:1–20`, `metrics.py:1–22`):** open `dedupe.py` (and the
pure part of `multipass.py`) with a docstring stating *pure, total, deterministic, stdlib-only, never raises,
unit-tests offline with no CLI/credentials*.

**Pure-core / live-driver split within one module (mirror `metrics.py`):** `multipass.py` keeps `split_diff`
(pure, top-level, imports only stdlib + `parse`/`dedupe`/`severity`) separate from the live driver functions
(`review_per_file`/`review_integration`/`review_multipass`) which do the `claude -p` calls. Import `runner`,
`schema`, `config`, `workspace` at the **top** of `multipass.py` (none touch the CLI at import time) so tests can
`monkeypatch.setattr(multipass.runner, "invoke_claude", fake)`.

**Path-suffix normalization (mirror `metrics._same_file`, lines 49–54) — copy it verbatim into `dedupe.py`:**
```python
def _same_file(a: str, b: str) -> bool:
    a = (a or "").replace("\\", "/").lstrip("./")
    b = (b or "").replace("\\", "/").lstrip("./")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)
```
(It is a private 3-liner in `metrics.py`; replicating it keeps `dedupe.py` self-contained and pure. Do not
create a shared util module for one function.)

**Constants with `#:` doc-comments citing the TR (mirror `config.py:44–61`).**

**Assert on structure/outcomes, never model wording (PRD principle 5).** Offline orchestration tests assert on
*call counts, sub-diff routing, and merged/deduped structure* via monkeypatch — no live model, fully
deterministic.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (verify + pure cores)
Verify the P1/P2 spine, add config constants, then the two pure modules (`dedupe.py`, `split_diff` in
`multipass.py`) and `store.py` — all offline-testable before any I/O or live calls.
**Tasks:** verify interfaces; extend `config.py`; `dedupe.py`; `multipass.split_diff`; `store.py`.

### Phase 2: Multipass orchestration + integration prompt (TR6/TR7)
The integration prompt, then the live driver functions that fan out per-file passes + the integration pass and
merge/dedupe/canonicalize.
**Tasks:** `review-integration.md`; `multipass` live driver (`review_per_file`/`review_integration`/
`review_multipass`) + demo drivers.

### Phase 3: Integration (CLI + store wiring + Make)
Wire `--mode`/`--pr-id`/dedupe into `cli.py` preserving all defaults; add Make targets.
**Tasks:** `cli.py`; `Makefile` (`review-multi`, `dedupe-demo`).

### Phase 4: Testing & Validation
Offline unit suite (split, orchestration-via-monkeypatch, dedupe, store) + the live acceptance demos + record
the results.
**Tasks:** `test_multipass.py`; `test_dedupe.py`; `test_store.py`; `test_multipass_live.py`; run demos;
update `_tasks/todo.md`.

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task is atomic and independently testable. `PY=../../.venv/bin/python`;
run from the project root; modules run with `PYTHONPATH=src/review` (see `Makefile:2`).

### VERIFY Phase-1/2 interfaces (do this FIRST — do not skip)
- **IMPLEMENT**: Read the ACTUAL `src/review/{config,schema,parse,runner,severity,metrics,cli,workspace,post}.py`
  and reconcile the names/signatures with the "CONTEXT REFERENCES" list above — especially `Finding` field order,
  `invoke_claude(prompt, schema_json, model, timeout_s, cwd=None)`, `parse_result(stdout) -> ParsedReview`,
  `severity.apply_canonical_severity`/`sort_by_severity`, `metrics._same_file`/`match`/`score(single_pass=)`,
  `workspace.staged`. If anything drifted, adapt the tasks below — **the real code wins.**
- **VALIDATE**:
  ```bash
  ../../.venv/bin/python -m pytest -m "not integration" -q   # expect: 53 passed (P1+P2 offline green)
  PYTHONPATH=src/review ../../.venv/bin/python -c "import config,schema,parse,runner,severity,metrics,cli,workspace,post; from parse import Finding,Location; import inspect; print('cwd' in inspect.signature(runner.invoke_claude).parameters, [f for f in Finding.__dataclass_fields__])"
  ```
  → expect `True ['location', 'issue', 'severity', 'suggested_fix', 'detected_pattern', 'category']`

### UPDATE `src/review/config.py` (add Phase-3a constants)
- **IMPLEMENT**: ADD after the Phase-2 constants (with `#:` doc-comments citing the TR):
  - `INTEGRATION_PROMPT = PROJECT_ROOT / ".claude" / "commands" / "review" / "review-integration.md"` — the
    cross-file integration-pass prompt (TR6).
  - `PRIOR_FINDINGS_DIR = PROJECT_ROOT / "data" / "prior_findings"` — per-PR prior-findings store (TR8/FR3).
  - `DEDUPE_LINE_TOLERANCE = 3` — two findings are the same issue if same file + same `detected_pattern` and
    `|line diff| <= this`. Set equal to `LINE_MATCH_TOLERANCE` deliberately (same "±a few lines" reasoning);
    reference that constant's rationale in the comment. **Note in the comment**: line drift *beyond* tolerance
    across commits is handled by the prompt-context dedupe layer (prior findings fed to the model), not the
    structural key — the two-layer design.
- **PATTERN**: `config.py:44–61` (`#:` comments + `PROJECT_ROOT / ...` paths).
- **IMPORTS**: none new (`Path`, `PROJECT_ROOT` already present).
- **GOTCHA**: Do NOT reuse `METRICS_DIR` for prior findings — they are different stores with different
  lifecycles. `PRIOR_FINDINGS_DIR` is written on every dedupe-enabled run; `METRICS_DIR` only by `make metrics`.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import config; print(config.INTEGRATION_PROMPT.name, config.PRIOR_FINDINGS_DIR.name, config.DEDUPE_LINE_TOLERANCE)"`
  → expect `review-integration.md prior_findings 3`

### CREATE `src/review/dedupe.py` (pure within-run + cross-run dedupe — TR8/FR3)
- **IMPLEMENT**: A **pure, total, deterministic, stdlib-only** module (docstring says so; never raises; no CLI):
  - `_same_file(a, b) -> bool` — copy verbatim from `metrics.py:49–54` (self-contained; note the origin in a
    comment).
  - `is_duplicate(a: Finding, b: Finding, tolerance: int) -> bool` — True iff `_same_file(a.location.file,
    b.location.file)` AND `a.detected_pattern == b.detected_pattern` (exact slug match — our controlled
    vocabulary) AND `abs(a.location.line - b.location.line) <= tolerance`. **Empty `detected_pattern` on both:**
    treat as non-matching unless file+line coincide (avoid collapsing unrelated unslugged findings) — so also
    require `detected_pattern` be non-empty for the pattern-equality branch; if either pattern is empty, fall
    back to `_same_file AND line within tolerance` only. Document this.
  - `dedupe(findings: list[Finding], *, tolerance: int) -> list[Finding]` — collapse duplicates **within** a list
    (per-file + integration overlap). Stable: keep the FIRST occurrence of each duplicate group (callers order
    findings so the integration/higher-value pass can be placed first if desired — but do not depend on it here;
    just keep-first, stable). Pure — returns a new list, never mutates inputs.
  - `suppress_prior(findings: list[Finding], prior: list[Finding], *, tolerance: int) -> tuple[list[Finding],
    list[Finding]]` — returns `(new, still_unresolved)`: `new` = findings NOT matching any `prior` finding (the
    genuinely new/first-time issues to comment); `still_unresolved` = findings that DID match a prior one
    (already reported → **not** re-commented, but tracked so callers can report "N still-unresolved"). This is
    the TR8/FR3 core: a re-run with the same unresolved issues yields an EMPTY `new` list → zero duplicate
    comments.
- **PATTERN**: `severity.py` (pure/deterministic module shape); `metrics.match`/`_same_file` for the matching
  logic. Result as a plain tuple (no dataclass needed — mirrors `severity` returning lists).
- **IMPORTS**: `from parse import Finding` (flat — `src/review` on path). **Do NOT import `runner`/`subprocess`/
  `config`** — pure and offline. (`tolerance` is passed in by callers, which read it from `config`.)
- **GOTCHA**: Match on `detected_pattern` (our controlled slug), NOT on `issue` prose (the model rewords it every
  run — matching prose would make dedupe nondeterministic). `apply_canonical_severity` is applied by the caller
  *before* dedupe so severity is never part of the identity (a re-run mustn't be a "new" finding just because
  the model relabeled severity — canonicalization already fixed that).
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "from parse import Finding,Location; import dedupe; a=Finding(Location('src/orders.py',24),'x','high','f','none-deref','correctness'); b=Finding(Location('orders.py',25),'y','high','f','none-deref','correctness'); print(dedupe.is_duplicate(a,b,3), len(dedupe.dedupe([a,b],tolerance=3)), [len(x) for x in dedupe.suppress_prior([a],[b],tolerance=3)])"`
  → expect `True 1 [0, 1]`  (a≈b are dupes; within-run collapses to 1; suppress → 0 new, 1 still-unresolved)

### CREATE `src/review/store.py` (persist/load prior findings — TR8/FR3)
- **IMPLEMENT**: A small persistence helper (filesystem, so NOT in pure `dedupe.py`):
  - `_pr_id(diff_path: str) -> str` — derive a stable id from a diff path = the filename stem with non-alnum
    chars replaced by `-` (e.g. `fixtures/sample-repo/pr.diff` → `pr`). Used when `--pr-id` isn't given.
  - `finding_to_dict(f: Finding) -> dict` — `{"location": {"file":…, "line":…}, "issue":…, "severity":…,
    "suggested_fix":…, "detected_pattern":…, "category":…}` (use `dataclasses.asdict(f)` — it recurses into the
    nested `Location`, giving exactly this shape).
  - `finding_from_dict(d: dict) -> Finding` — `Finding(Location(d["location"]["file"], d["location"]["line"]),
    d["issue"], d["severity"], d["suggested_fix"], d["detected_pattern"], d["category"])`.
  - `save_findings(pr_id: str, findings: list[Finding], *, base_dir: Path = None) -> Path` — write
    `{base_dir or config.PRIOR_FINDINGS_DIR}/{pr_id}.json` (`mkdir(parents=True, exist_ok=True)`),
    `json.dumps({"pr_id": pr_id, "findings": [finding_to_dict(f) ...]}, indent=2)`. Return the path.
  - `load_prior(pr_id: str, *, base_dir: Path = None) -> list[Finding]` — read that file; return
    `[finding_from_dict(d) ...]`; **missing file → `[]`** (first run has no prior — never raise).
- **PATTERN**: `metrics._write_metrics`/`_load_cases` (lines 225–251) for the read/write + `mkdir` idiom; the
  `base_dir` override mirrors how tests point at a tmp dir instead of the repo store.
- **IMPORTS**: `json`, `import config`, `from dataclasses import asdict`, `from pathlib import Path`,
  `from parse import Finding, Location`.
- **GOTCHA**: The `base_dir` kwarg exists so `test_store.py` writes under `$TMPDIR`, never polluting the repo's
  `data/prior_findings/`. Default `None` → `config.PRIOR_FINDINGS_DIR` (production path). Round-trip must be
  loss-free: assert `load_prior(save_findings(...))` equals the input (dataclass `==` is field-wise).
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import tempfile,pathlib,store; from parse import Finding,Location; d=pathlib.Path(tempfile.mkdtemp()); f=[Finding(Location('src/orders.py',24),'x','high','fix','none-deref','correctness')]; store.save_findings('pr',f,base_dir=d); print(store.load_prior('pr',base_dir=d)==f, store.load_prior('missing',base_dir=d))"`
  → expect `True []`

### CREATE `src/review/multipass.py` — pure `split_diff` (TR6 foundation)
- **IMPLEMENT**: The pure diff splitter at module top (stdlib + `parse` only in this part):
  - `@dataclass FileDiff: path: str; text: str` — one file's self-contained sub-diff.
  - `split_diff(diff_text: str) -> list[FileDiff]` — split a unified diff into per-file chunks:
    1. Split on lines beginning `diff --git ` (each such line starts a new file chunk; keep the line with its
       chunk). If the diff has **no** `diff --git ` markers (a bare `--- /+++ ` diff), fall back to splitting on
       `--- ` boundaries; if still one chunk, return it as a single `FileDiff`.
    2. For each chunk, derive `path`: prefer the `+++ b/<path>` line's path (strip the `b/` prefix); if that is
       `/dev/null` (deletion), use the `--- a/<path>` path. If neither present, use the `diff --git a/… b/…`
       b-path.
    3. Return the list in source order. Empty/whitespace-only input → `[]`.
  - This is **pure and offline-testable** — no CLI, no I/O.
- **PATTERN**: `severity.py`/`metrics.py` pure-core style; the fixture `pr.diff` (lines 1, 30, 46, 75 are the
  `diff --git` boundaries — 4 files) is the canonical shape to split correctly.
- **IMPORTS** (top of module, pure section): `from dataclasses import dataclass`. (Live-driver imports below.)
- **GOTCHA**: Preserve each chunk's leading `diff --git`/`---`/`+++`/`@@` headers verbatim — the per-file prompt
  needs valid diff structure and correct new-file line numbers. Do NOT re-number hunks. Diffs contain `{`/`}` →
  never `str.format`; the driver uses `.replace("{diff}", chunk.text)` (P1/P2 decision).
- **VALIDATE** (after this task; before the live driver): `PYTHONPATH=src/review ../../.venv/bin/python -c "import multipass; d=open('fixtures/sample-repo/pr.diff').read(); fds=multipass.split_diff(d); print(len(fds), [f.path for f in fds])"`
  → expect `4 ['src/orders.py', 'src/settings.py', 'src/ingest.py', 'src/summary.py']`

### CREATE `.claude/commands/review/review-integration.md` (the integration-pass prompt — TR6)
- **IMPLEMENT**: A versioned command (frontmatter `---\ndescription: …\n---`) for the **cross-file integration
  pass**. It sees the WHOLE diff and is told to report **only cross-file / data-flow / cross-module-contract**
  issues, explicitly NOT single-file issues (those are the per-file passes' job) — this minimizes overlap and
  contradictory findings. Contents:
  - Role: "You are reviewing an ENTIRE pull-request diff spanning multiple files, specifically for defects that
    only appear when reasoning ACROSS files. Single-file issues are handled by a separate per-file review — do
    NOT report them here."
  - Honor the project `CLAUDE.md` conventions (loaded from cwd) — same TR3 respect clause as `review-diff.md`.
  - **FLAG only cross-file issues** with concrete triggers: a producer writes a dict key / field / arg that a
    consumer in another file reads under a *different* name (→ `KeyError`/`AttributeError`); a function's
    signature or return shape changed in one file but a caller in another file wasn't updated; an
    enum/constant/contract defined in one file used inconsistently in another.
  - **DON'T flag**: anything visible within a single file in isolation; style; hypotheticals with no concrete
    cross-file trigger.
  - **One few-shot pair (TR4 discipline):** *Finding* — `ingest.to_record` writes `"user_id"`, `summary.user_ids`
    reads `rec["userId"]` → runtime `KeyError`; `detected_pattern: cross-file-key-mismatch`, `severity: critical`,
    `category: correctness`. *No finding* — a producer writes `"user_id"` and every consumer reads `"user_id"`.
    (This teaches the discrimination; the fixture is the same *class*, not a memorized answer.)
  - **Severity rubric**: reuse the four-level rubric from `review-diff.md` (a cross-module contract break that
    crashes a production path = `critical`).
  - **Field guidance**: identical to `review-diff.md` (`location.file` = `+++ b/` path; `location.line` = new-file
    line; `detected_pattern` from the controlled set — `cross-file-key-mismatch` etc.; `category`).
  - End with the same ` ```diff\n{diff}\n``` ` placeholder block.
- **PATTERN**: `review-diff.md` (whole file) — mirror its structure, frontmatter, few-shot format, severity
  rubric, and field guidance; change only the *scope* (cross-file only) and the few-shot.
- **GOTCHA**: `detected_pattern: cross-file-key-mismatch` MUST match `severity.PATTERN_SEVERITY` key (line 60) so
  the canonical override maps it to `critical` — align the slug exactly. Prompt text is NEVER asserted on in
  tests (validation is structural); refine wording freely to make the integration pass reliably catch the seeded
  bug on haiku.
- **VALIDATE**: `grep -q '{diff}' .claude/commands/review/review-integration.md && grep -qi 'cross-file' .claude/commands/review/review-integration.md && echo OK`

### CREATE `src/review/multipass.py` — live driver (TR6/TR7 orchestration)
- **IMPLEMENT**: Below `split_diff`, the live orchestrator. Import `runner`, `schema`, `config`, `parse`,
  `severity`, `dedupe` at the **top** of the module (none call the CLI at import — enables monkeypatch). Add a
  private helper to run one pass:
  - `_run_pass(prompt_template: str, diff_text: str, model: str, cwd: str | None) -> list[Finding]` —
    `prompt = prompt_template.replace("{diff}", diff_text)`; `result = runner.invoke_claude(prompt,
    schema.as_json_string(), model, config.CLAUDE_TIMEOUT_S, cwd=cwd)`; `review = parse.parse_result(result.stdout)`;
    return `[]` if `review.is_error` else `review.findings`. (Reuse `cli._strip_frontmatter` logic — replicate
    the 6-line frontmatter strip as a local `_strip_frontmatter` here, or import it; prefer a local copy to keep
    modules decoupled, matching how `metrics.py:179–185` has its own `_strip_frontmatter`.)
  - `review_per_file(diff_text, prompt_path, model, *, cwd=None) -> list[Finding]` — `split_diff(diff_text)`;
    for EACH `FileDiff`, call `_run_pass(<enriched template>, fd.text, model, cwd)` — **a separate
    `invoke_claude` per file = a fresh independent instance (TR7)**; concatenate all findings; return
    `dedupe.dedupe(all, tolerance=config.DEDUPE_LINE_TOLERANCE)`. (Sequential is fine and deterministic for the
    fixture; a comment notes the passes are independent and *could* be parallelized.)
  - `review_integration(diff_text, integration_prompt_path, model, *, cwd=None) -> list[Finding]` — ONE
    `_run_pass(<integration template>, diff_text /* whole diff */, model, cwd)`. A fresh instance (TR7).
  - `review_multipass(diff_text, *, prompt_path=config.ENRICHED_PROMPT, integration_prompt_path=config.INTEGRATION_PROMPT, model, cwd=None) -> list[Finding]` —
    `per_file = review_per_file(...)`; `integ = review_integration(...)`; merge `integ + per_file` (integration
    first so its cross-file finding wins keep-first on any overlap), `apply = severity.apply_canonical_severity(merged)`,
    `deduped = dedupe.dedupe(apply, tolerance=config.DEDUPE_LINE_TOLERANCE)`, return
    `severity.sort_by_severity(deduped)`.
  - **Live demo drivers** (mirror `metrics.run_metrics`/`run_tr3_demo`; local imports inside for `workspace`,
    `metrics`, `store`):
    - `run_multipass_demo() -> dict` (`make review-multi`): stage `config.FIXTURE_REPO` (CLAUDE.md present) once,
      run `review_multipass` on `pr.diff` with `cwd=staged`, `score` (via `metrics.score(..., single_pass=False)`)
      against `ground_truth.json`, print the findings + whether `cross-file-key-mismatch` is now a TP, write
      `data/metrics/multipass.json`. Headline artifact: "cross-file bug caught by integration pass: True".
    - `run_dedupe_demo() -> dict` (`make dedupe-demo`): run `review_multipass` on `pr.diff` → `first`; save via
      `store.save_findings("demo", first)`; run `review_multipass` again → `second`; `new, still =
      dedupe.suppress_prior(second, store.load_prior("demo"), tolerance=config.DEDUPE_LINE_TOLERANCE)`; print
      "second-run NEW comments (should be ~0): len(new); still-unresolved suppressed: len(still)". Headline:
      "duplicate comments on re-run: len(new)".
- **PATTERN**: `metrics.run_variant` (188–222) for the staged-workspace + invoke + parse + canonical-severity
  live-driver shape; `metrics.run_tr3_demo` (280–326) for the demo-driver + write-JSON shape.
- **IMPORTS**: top: `from dataclasses import dataclass`, `import config, parse, runner, schema, severity, dedupe`.
  Inside demo drivers: `import workspace, metrics, store`, `from pathlib import Path`.
- **GOTCHA**: (1) **TR7 is a hard invariant** — every pass MUST be its own `invoke_claude` call; never add
  `--continue`/`--resume`/session reuse, and never pass one pass's output into another pass's prompt (that would
  reintroduce shared reasoning context). (2) All passes share ONE staged workspace/`cwd` (cheaper; independence
  is about process/context, not the filesystem). (3) `apply_canonical_severity` BEFORE `dedupe` so a per-file and
  an integration report of the same pattern carry identical severity and collapse cleanly (no contradictory
  findings). (4) Keep `_run_pass` tolerant of an empty/error review (`review.is_error` → `[]`) so one bad pass
  doesn't sink the whole run.
- **VALIDATE** (offline smoke via monkeypatch — no live call): see `test_multipass.py`. Quick import check:
  `PYTHONPATH=src/review ../../.venv/bin/python -c "import multipass, inspect; print([n for n in ('split_diff','review_per_file','review_integration','review_multipass') if hasattr(multipass,n)]); print('cwd' in inspect.signature(multipass.review_multipass).parameters)"`
  → expect all four names + `True`

### UPDATE `src/review/cli.py` (add `--mode`, `--pr-id`, dedupe branch — preserve all defaults)
- **IMPLEMENT**: ADD argparse options and branch, WITHOUT changing the default behavior:
  - `--mode {single,multi}` default `single`. `single` = the existing Phase-1/2 path (unchanged). `multi` =
    call `multipass.review_multipass(diff, prompt_path=<selected>, model=args.model, cwd=cwd)` instead of the
    single `runner.invoke_claude`. (The per-file prompt is the selected `--prompt` template; the integration
    prompt is `config.INTEGRATION_PROMPT`.)
  - `--pr-id <str>` default `None`. When provided (OR when you choose to always derive it — but default OFF to
    preserve behavior), **enable dedupe**: after producing `findings` (single or multi) and applying canonical
    severity + sort, do `prior = store.load_prior(args.pr_id)`; `new, still =
    dedupe.suppress_prior(findings, prior, tolerance=config.DEDUPE_LINE_TOLERANCE)`; `emit(new)`; print a one-line
    note `f"({len(still)} still-unresolved finding(s) suppressed as duplicates)"` to stderr; then
    `store.save_findings(args.pr_id, findings)` (persist the FULL current set — including still-unresolved — as
    the prior for the next run, so the next re-run suppresses them too). When `--pr-id` is absent → **no dedupe,
    no store I/O** (byte-for-byte the Phase-2 emit path).
  - Keep `--diff`, `--model`, `--prompt`, `--repo`, `load_env`, the `ExitStack` staged-cwd, and ALL
    timeout/exit-code/`is_error` handling intact. In `multi` mode the timeout is per-pass (each `invoke_claude`
    already has the backstop); wrap the whole multipass call in the same `try/except subprocess.TimeoutExpired`
    → clean exit 1.
- **PATTERN**: `cli.py:48–144` — add the args in the same argparse block; branch on `args.mode` where the single
  `invoke_claude` currently is (lines 102–124); apply dedupe between `apply_canonical_severity`/`sort` (line 141)
  and `emit` (line 143).
- **IMPORTS**: `import dedupe, multipass, store` (flat). Reuse existing.
- **GOTCHA**: The default (`--mode single`, no `--pr-id`) MUST keep `make ci-review PR=fixtures/pr-01/sample.diff`
  and all Phase-1/2 tests passing identically — verify with the Level-2 suite. In `multi` mode a single-file diff
  still works (`split_diff` → 1 chunk → 1 per-file pass + 1 integration pass). Do not stage a workspace unless
  `--repo` is given (multi mode without `--repo` runs in cwd, same as single) — the metrics/live tests pass
  `--repo`/`cwd` explicitly via the driver, not the CLI.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -m cli --help` (shows `--mode`, `--pr-id`; exit 0);
  then `PYTHONPATH=src/review ../../.venv/bin/python -m pytest tests/test_cli.py -q` (Phase-1 CLI tests still green).

### UPDATE `Makefile` (add `review-multi` + `dedupe-demo`; keep `test-gen` stub)
- **IMPLEMENT**: ADD targets (TABS, not spaces) + add to `.PHONY`:
  - `review-multi:` → `PYTHONPATH=$(PYTHONPATH) $(PY) -c "import multipass; multipass.run_multipass_demo()"`
  - `dedupe-demo:` → `PYTHONPATH=$(PYTHONPATH) $(PY) -c "import multipass; multipass.run_dedupe_demo()"`
  - Add a comment (mirroring the `metrics`/`tr3-demo` comment block, lines 25–27) that these make LIVE `claude -p`
    calls (need CLI + `ANTHROPIC_API_KEY`, haiku tier, multiple passes = higher cost) and are NOT run by
    `make test`. Leave the `test-gen` stub as-is (that's Phase 3b).
- **PATTERN**: `Makefile:28–32` (`metrics`/`tr3-demo` targets + `.PHONY` + the live-call comment).
- **GOTCHA**: `review-multi` fans out N per-file passes + 1 integration pass = N+1 model calls per run;
  `dedupe-demo` runs multipass TWICE. Note the cost in the comment.
- **VALIDATE**: `make -n review-multi && make -n dedupe-demo` (dry-run prints the commands).

### CREATE `tests/test_multipass.py` (OFFLINE — split + orchestration via monkeypatch; TR6/TR7)
- **IMPLEMENT**: No live calls — monkeypatch `multipass.runner.invoke_claude`.
  - **split_diff**: on `fixtures/sample-repo/pr.diff` → 4 `FileDiff` with paths `src/orders.py`, `src/settings.py`,
    `src/ingest.py`, `src/summary.py`, each `text` containing its own `@@` hunk; a single-file diff (Phase-1
    `fixtures/pr-01/sample.diff`) → 1 chunk; empty string → `[]`. Assert each chunk round-trips (`"".join` of
    texts contains all four paths).
  - **orchestration (the TR7 proof)**: define a `fake_invoke(prompt, schema_json, model, timeout_s, cwd=None)`
    that returns a canned `RunResult` whose stdout is a minimal valid CLI event array (one `{"type":"result",
    "structured_output":{"findings":[…]}}`), choosing findings based on which file's diff is in `prompt` (e.g.
    orders → a `none-deref` finding; ingest/summary/settings → empty; the integration prompt → a
    `cross-file-key-mismatch` finding). Monkeypatch it, then:
    - `review_per_file(pr_diff, ENRICHED_PROMPT, model)` calls `invoke_claude` **exactly 4 times** (once per
      file) and each call's `prompt` contains ONLY that file's sub-diff (assert `"src/summary.py"` not in the
      orders call's prompt, etc.) → **proves isolation**. Result contains the `none-deref` finding and NOT
      `cross-file-key-mismatch` (per-file can't see it) → **proves per-file misses cross-file**.
    - `review_integration(pr_diff, INTEGRATION_PROMPT, model)` calls `invoke_claude` **exactly once** with the
      WHOLE diff → returns the `cross-file-key-mismatch` finding.
    - `review_multipass(...)` calls `invoke_claude` **exactly 5 times** (4 + 1 — the independent-instance count)
      and its merged/deduped result contains BOTH `none-deref` (high) and `cross-file-key-mismatch` (critical),
      each **once** (dedupe collapses the integration/per-file overlap if the fake emits none-deref in both).
    - Use a call-counter (list appended in `fake_invoke`, or `unittest.mock.MagicMock` wrapping it) to assert the
      counts — this is the deterministic TR7 evidence (N+1 separate calls, no session reuse).
  - **canonical severity + no contradiction**: have the fake emit `none-deref` with `severity:"low"` in one pass
    and `severity:"high"` in another; assert the merged result has it exactly once at `high` (canonicalized) —
    proves "no contradictory findings".
- **PATTERN**: `test_metrics.py` `_f(...)` finding-builder + structural assertions; `runner.RunResult` shape
  (`runner.py:14–25`) for the canned output; `tests/fixtures/sample_claude_output.json` for a real event-array
  shape to imitate.
- **GOTCHA**: Monkeypatch `multipass.runner.invoke_claude` (the name multipass resolved at import), not
  `runner.invoke_claude` globally — use `monkeypatch.setattr(multipass.runner, "invoke_claude", fake)`. The fake
  must return a `runner.RunResult` (import it) so `parse.parse_result(result.stdout)` works. This test needs NO
  `claude` CLI and NO key → runs under `-m "not integration"`.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_multipass.py -q`

### CREATE `tests/test_dedupe.py` (OFFLINE — TR8/FR3)
- **IMPLEMENT**: Hand-authored `Finding` lists (a local `_f(file,line,pattern)` helper like `test_metrics.py:38`):
  (1) `is_duplicate` True for same file + same pattern within tolerance, False when pattern differs, False when
  line diff > tolerance, True across suffix path forms (`orders.py` vs `src/orders.py`); (2) empty-pattern
  fallback (two empty-pattern findings dupe only on file+line-within-tolerance); (3) `dedupe` collapses a
  within-run duplicate pair to one (keep-first, stable) and leaves distinct findings untouched; (4)
  `suppress_prior` returns `(new=[], still=[f])` when the only finding matches a prior one → **zero duplicate
  comments** (the headline TR8 assertion); (5) `suppress_prior` returns the genuinely-new finding in `new` when
  it doesn't match any prior; (6) no mutation of inputs (assert original lists unchanged). `@pytest.mark.parametrize`
  the tolerance/suffix table.
- **PATTERN**: `test_metrics.py` (whole file) — builder + structural assertions, no CLI.
- **GOTCHA**: This test is the **deterministic guarantee** behind "second commit → zero duplicate comments" —
  treat a failure as a correctness bug. Assert on `detected_pattern`-based identity, never on `issue` prose.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_dedupe.py -q`

### CREATE `tests/test_store.py` (OFFLINE — TR8/FR3 persistence)
- **IMPLEMENT**: Using a `tmp_path` (pytest builtin) as `base_dir`: (1) `save_findings` then `load_prior`
  round-trips a `Finding` list loss-free (dataclass `==`, all six fields incl. nested `Location`); (2)
  `load_prior` of an unknown `pr_id` → `[]` (no raise — first run); (3) `save_findings` creates the dir if
  absent; (4) `_pr_id("fixtures/sample-repo/pr.diff")` → `"pr"`. Do NOT write to the real
  `config.PRIOR_FINDINGS_DIR`.
- **PATTERN**: `test_metrics.py` structure; `tmp_path` fixture for the `base_dir` override.
- **GOTCHA**: Always pass `base_dir=tmp_path` so the repo store isn't polluted — a test that writes to
  `data/prior_findings/` would leak state across runs and break determinism.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_store.py -q`

### CREATE `tests/test_multipass_live.py` [integration] (TR6/TR7/TR8 acceptance demos)
- **IMPLEMENT**: `pytestmark = [pytest.mark.integration, pytest.mark.skipif(shutil.which("claude") is None, …)]`
  (mirror `test_precision_live.py:21–27`), `model=config.BASELINE_MODEL` (haiku, cost cap). Stage the fixture
  via `workspace.staged(config.FIXTURE_REPO, include_claude_md=True)` and pass `cwd` to the drivers. Tests:
  1. **Per-file isolation MISSES cross-file (TR6/TR7):** `review_per_file(pr.diff, ENRICHED_PROMPT, model,
     cwd=…)`; assert NO finding matches the `cross-file-key-mismatch` case (`metrics.match`) — each file in
     isolation cannot see it. (It SHOULD contain `none-deref`.)
  2. **Integration pass CATCHES cross-file (TR6):** `review_integration(pr.diff, INTEGRATION_PROMPT, model,
     cwd=…)`; assert a finding matches the `cross-file-key-mismatch` case. → With #1, proves "caught ONLY by the
     integration pass."
  3. **Multipass merged result scores clean (TR6):** `review_multipass(...)`; `metrics.score(findings, cases,
     tolerance=…, single_pass=False)`; assert `cross-file-key-mismatch` in `matched` (now a **TP**, not a known
     gap), `none-deref` in `matched`, and the `settings-broad-except` case NOT flagged (CLAUDE.md present) → no
     FP; assert each matched pattern appears once (no contradictory/duplicate findings).
  4. **Dedupe across re-runs → zero duplicates (TR8/FR3):** run `review_multipass` twice on `pr.diff`;
     `save_findings("test-live", first)`; `new, still = dedupe.suppress_prior(second, load_prior("test-live"),
     tolerance=…)`; assert the `none-deref` case is NOT in `new` (already reported → suppressed) and IS in `still`
     — i.e. **zero duplicate comments for the previously-reported issue** on the second run. (Assert on the
     `none-deref` case specifically — reliably caught in both runs — for robustness against model
     nondeterminism.) Use `base_dir=tmp_path` for the store so the repo isn't polluted.
- **PATTERN**: `test_precision_live.py` (whole file) — integration gating, `metrics.match`/`score` usage, "assert
  on outcomes never prose".
- **GOTCHA**: These calls cost money and are non-deterministic. #1 (per-file misses) is essentially guaranteed by
  isolation; #2 (integration catches) is the empirical risk on haiku — **if it's flaky, iterate the
  `review-integration.md` wording** (the fixture/prompt is ground truth; calibrating it is the work) or, as a
  documented fallback, run ONLY the integration pass on `config.REVIEW_MODEL` (sonnet). Never loosen the assert to
  make a bad prompt pass. #4's determinism lives in `test_dedupe.py`; the live version just proves the real
  re-run produces suppressible dupes.
- **VALIDATE**:
  ```bash
  export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
  ../../.venv/bin/python -m pytest -m integration tests/test_multipass_live.py -q
  ```

### CREATE `data/prior_findings/.gitkeep` + UPDATE `.gitignore`
- **IMPLEMENT**: `touch data/prior_findings/.gitkeep` (keep the dir tracked). ADD to `.gitignore`:
  `data/prior_findings/*.json` (runtime artifacts — the store is written on every dedupe run; don't commit
  transient prior-findings). Mirror however `data/metrics/*.json` is handled (check current `.gitignore`; if
  metrics json are committed, match that convention instead — be consistent).
- **VALIDATE**: `test -f data/prior_findings/.gitkeep && git check-ignore data/prior_findings/pr.json && echo OK`
  (the last command prints the path if ignored; adjust if the repo convention is to commit them).

### UPDATE `_tasks/todo.md`
- **IMPLEMENT**: Add a "Phase 3a — Scale + Dedupe (TR6/TR7/TR8/FR3)" checklist mirroring these tasks; mark
  complete as you go; append a review section (what worked / what didn't / the recorded results: did the
  integration pass catch the cross-file bug on haiku? zero duplicates on re-run? any prompt calibration needed?).
  Note that FR2 test-gen is Phase 3b.
- **VALIDATE**: `test -f _tasks/todo.md`

---

## TESTING STRATEGY

### Unit Tests (offline, default `-m "not integration"` — MUST pass with zero network/CLI)
- **multipass** (`test_multipass.py`): `split_diff` correctness (4-file, single-file, empty); **orchestration via
  monkeypatched `invoke_claude`** — the fan-out shape (4 per-file + 1 integration = 5 independent calls, the TR7
  proof), per-file prompt isolation (each call sees only its sub-diff → misses cross-file), merged+deduped result
  (cross-file present once, canonical severity, no contradictions). **No live model** — deterministic.
- **dedupe** (`test_dedupe.py`): `is_duplicate`/`dedupe`/`suppress_prior` over hand-authored findings; the
  "zero duplicate comments on re-run" assertion; tolerance + suffix matching; empty-pattern fallback; no mutation.
- **store** (`test_store.py`): loss-free `Finding` round-trip; missing pr_id → `[]`; dir creation; `base_dir`
  override so the repo store is never touched.
- All: assertions on structure/constants; **never on model wording** (PRD principle 5).

### Integration Tests (`-m integration`, gated on `claude_runnable()`, haiku tier)
- **multipass-live** (`test_multipass_live.py`): the four acceptance demos — per-file misses cross-file,
  integration catches it, multipass scores clean (cross-file now a TP), re-run yields zero duplicate comments.
  Assert on outcomes/structure only.

### Edge Cases (must be covered)
- Single-file diff through `--mode multi` → 1 per-file pass + 1 integration pass; still works, no crash.
- One pass returns an `is_error` envelope → `_run_pass` yields `[]`; multipass continues (one bad pass ≠ total
  failure).
- Per-file + integration both report the same `none-deref` (integration sees the whole diff) → dedupe collapses
  to one; canonical severity identical → no contradiction.
- Re-run with prior findings covering ALL current findings → `new == []` (zero duplicate comments) — the FR3 gate.
- First run (no prior file) → `load_prior` returns `[]`, everything emitted, then persisted.
- Empty diff / whitespace → `split_diff` returns `[]`; multipass returns `[]` gracefully.
- Finding path reported bare (`orders.py`) vs `src/orders.py` → `dedupe._same_file` suffix-matches (dupes still
  collapse across path forms).

---

## VALIDATION COMMANDS

Run from the project root (`.../projects/claude-code-ci-review-bot`). `PY=../../.venv/bin/python`.

### Level 1: Syntax & Style
```bash
../../.venv/bin/python -m py_compile src/review/*.py tests/*.py
# (no ruff/black in the shared venv — py_compile is the syntax gate, per Phase 1/2)
```

### Level 2: Unit Tests (offline — MUST pass with zero network/CLI; includes all P1/P2 tests)
```bash
../../.venv/bin/python -m pytest -m "not integration" -q
# EXPECT: previous 53 + new offline tests, all passing; 0 requiring CLI/network.
```

### Level 3: Integration Tests (needs `claude` CLI + ANTHROPIC_API_KEY; haiku cost, N+1 calls per multipass)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
../../.venv/bin/python -m pytest -m integration tests/test_multipass_live.py -q
```

### Level 4: Manual Validation (the headline deliverables)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
make review-multi   # multipass on pr.diff; prints findings + "cross-file bug caught by integration pass: True"
make dedupe-demo    # runs multipass twice; prints "duplicate comments on re-run: 0"
```
EXPECT: `review-multi` shows the `cross-file-key-mismatch` finding present (now a scored TP under multipass) and
the `none-deref` finding, `settings-broad-except` NOT flagged; `dedupe-demo` shows zero new comments on the
second run.

### Level 5: Additional Validation (regression — Phase-1/2 behavior preserved)
```bash
# Default single-pass path unchanged:
make ci-review PR=fixtures/pr-01/sample.diff < /dev/null; echo "exit: $?"          # exit 0, 1 finding
# Multi mode end-to-end on the fixture PR (staged CLAUDE.md, non-interactive):
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
PYTHONPATH=src/review ../../.venv/bin/python -m cli --diff fixtures/sample-repo/pr.diff \
  --repo fixtures/sample-repo --mode multi --pr-id sample < /dev/null; echo "exit: $?"
# Re-run the same command → the still-unresolved note shows suppressed dupes; emitted NEW comments ~0.
```

---

## ACCEPTANCE CRITERIA

- [ ] **TR6 multi-pass:** the diff is split per-file; each file reviewed in its own pass; a separate integration
      pass reviews the whole diff. On the fixture, per-file passes do **NOT** flag `cross-file-key-mismatch` and
      the integration pass **DOES** → the cross-file bug is caught **only** by the integration pass.
- [ ] **TR7 independent instance:** `review_multipass` makes **N+1 independent `invoke_claude` calls** (N per-file
      + 1 integration), each a fresh process with no shared context; **no `--continue`/`--resume`/session reuse**
      and no pass consumes another pass's output. Proven deterministically in `test_multipass.py`.
- [ ] **No contradictory findings:** the merged multipass result contains each issue **once** with a single
      (canonical) severity; per-file/integration overlap is deduped.
- [ ] **TR8/FR3 dedupe:** on a re-run with prior findings, previously-reported still-unresolved issues produce
      **zero** new comments (`suppress_prior` → empty `new`); genuinely new issues still surface. Prior findings
      persist per PR in `data/prior_findings/`.
- [ ] **Multipass scores clean:** `metrics.score(multipass_findings, cases, single_pass=False)` has
      `cross-file-key-mismatch` and `none-deref` as TPs and `settings-broad-except` NOT flagged (no FP) with the
      fixture CLAUDE.md present.
- [ ] **Regression:** `make ci-review PR=fixtures/pr-01/sample.diff` and ALL Phase-1/2 tests pass **unchanged**
      (default `--mode single`, no `--pr-id` = byte-for-byte the Phase-2 path).
- [ ] Offline unit suite (`-m "not integration"`) passes with **no network/CLI**; integration suite passes when
      the CLI is available (skips cleanly otherwise).
- [ ] No `claude-agent-sdk` / `anthropic` / `gh` imports (CLI-as-agent; posting is Phase 4).
- [ ] The answer key still never reaches the model (staging still excludes `ground_truth.json`/`*.diff` — Phase-2
      `workspace.py` unchanged and reused).

---

## COMPLETION CHECKLIST
- [ ] Phase 1/2 verified present & green BEFORE starting; interfaces reconciled with the real code.
- [ ] All tasks completed in order; each task's `VALIDATE` passed immediately.
- [ ] Level 1–4 validation executed; `make review-multi` + `make dedupe-demo` produce the two demonstrable
      results (cross-file caught by integration; zero duplicates on re-run).
- [ ] Level 5 regression confirmed: default single-pass path + all P1/P2 tests unchanged.
- [ ] Offline unit suite green; integration suite green (or cleanly skipped).
- [ ] No linting/type errors (`py_compile` clean).
- [ ] `_tasks/todo.md` updated with a completion review (incl. whether haiku's integration pass caught the
      cross-file bug and any prompt calibration done).

---

## NOTES

**Decisions made during planning (with rationale):**
1. **Per-file *isolation* is the TR6 lever, not whole-diff re-review.** Phase 2 recorded that a whole-diff single
   pass can opportunistically catch the cross-file bug (so it was a *known gap*, precision-neutral). Phase 3a's
   per-file passes each see ONE file → they genuinely cannot connect `user_id`/`userId`, so the integration pass
   is the *only* one that catches it. This is the honest, reproducible TR6 demonstration.
2. **TR7 is satisfied by construction (process boundary), and proven offline.** Every pass is its own
   `claude -p` subprocess with no shared context; we never use `--continue`/`--resume` and never feed one pass's
   output into another's prompt. `test_multipass.py` asserts the N+1 independent call count via monkeypatch — a
   deterministic proof, no live cost.
3. **Orchestration is unit-tested offline by monkeypatching `invoke_claude`.** Mirrors the Phase-2 pure/live
   split: the fan-out shape, per-file prompt isolation, and merge/dedupe are proven with canned CLI output; only
   the real-model *behavior* (catches/misses/suppresses) needs the integration tier. Keeps the fast suite
   deterministic and free.
4. **Dedupe is two-layer, mirroring the proven severity pattern.** Structural `dedupe.py` (deterministic
   backstop, matched by file + `detected_pattern` + line-tolerance) is the guarantee behind "zero duplicate
   comments"; the prompt-context layer (prior findings fed to the model, "report only new/unresolved") handles
   semantic dupes across line drift. `detected_pattern` (our controlled slug), never `issue` prose, is the
   identity — prose is reworded every run.
5. **`apply_canonical_severity` runs BEFORE dedupe/merge** so a per-file and an integration report of the same
   pattern carry identical severity and collapse cleanly → "no contradictory findings" is structurally true, not
   hoped for.
6. **Defaults preserved: `--mode single`, no `--pr-id`.** The entire Phase-1/2 path (and its tests, and
   `make ci-review PR=fixtures/pr-01/sample.diff`) is untouched. Multipass and dedupe are opt-in — a wary
   engineer's tool must not silently change behavior on the small-PR path.
7. **All passes share one staged workspace/`cwd`.** Independence (TR7) is about reasoning context, which separate
   processes already guarantee; re-staging per pass would waste time/disk for no isolation benefit. The Phase-2
   `workspace.staged` + answer-key exclusion is reused verbatim.
8. **The scorer already supports this phase.** `metrics.score(..., single_pass=False)` turns the cross-file case
   from a known gap into an eligible positive — no scorer change needed; Phase 3a just feeds it the multipass
   result.

**Prerequisites & environment gotchas:**
- Phases 1 & 2 are on disk and green (53 offline passed). The first task re-verifies interfaces.
- Shared venv Python 3.10 at `../../.venv`; no new deps.
- No `ruff`/`black` → Level 1 is `py_compile` only.
- Integration/`make review-multi`/`dedupe-demo` make LIVE, MULTI-pass `claude -p` calls (haiku) — higher cost
  than Phase 2's single-pass demos (N+1 calls; dedupe-demo runs multipass twice). Not run by `make test`.
- Prompt calibration is empirical: if the integration pass doesn't reliably catch the cross-file bug on haiku,
  iterate `review-integration.md` wording (fixture/prompt is ground truth) or run the integration pass on sonnet
  as a documented fallback — never loosen the assert.

**Out of scope for Phase 3a (do not build):** test generation (FR2 — **Phase 3b**, separate plan);
`detected_pattern` dismissal tracking + category quarantine (TR9/FR4 — Phase 4); real `gh --post` (Phase 4);
parallel execution of per-file passes (sequential is fine for the MVP; noted as a future optimization).

**Confidence for one-pass execution:** **8/10.** The spine is solid and well-understood, the pure modules
(`dedupe`, `split_diff`, `store`) and the offline orchestration test are fully deterministic, and defaults are
preserved so regression risk is low. The one live-behavior risk is haiku's integration pass reliably catching
the cross-file bug (documented fallback: iterate the integration prompt or use sonnet for that one pass) — a
calibration task, not a design risk.
```
