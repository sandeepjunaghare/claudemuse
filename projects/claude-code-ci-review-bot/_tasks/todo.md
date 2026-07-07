# Tasks

## Phase 1 — Headless + Structured

Plan: `.agents/plans/phase-1-headless-structured.md`
Goal: prove non-interactive `claude -p` invocation + schema-valid parsing, with
findings mapped to `file:line`.

### Foundation
- [x] `requirements.txt` (pytest, python-dotenv, jsonschema — no SDK)
- [x] `pytest.ini` (testpaths=tests, `integration` marker, no asyncio)
- [x] `src/review/__init__.py`
- [x] `src/review/config.py` (`load_env` at `parents[4]`, `REVIEW_MODEL`, `CLAUDE_TIMEOUT_S`, `PROMPT_TEMPLATE`)
- [x] `src/review/schema.py` (`FINDINGS_SCHEMA`, `as_json_string`, `validate_findings_obj`)

### Core (invoke → parse → emit)
- [x] `src/review/runner.py` (`invoke_claude` → `RunResult`; stdout/stderr separate; timeout backstop)
- [x] `src/review/parse.py` (`Location`/`Finding`/`ParsedReview`; `parse_result`; `ParseError`; `structured_output` + fallback)
- [x] `src/review/post.py` (`format_comment`, `emit`; no gh)
- [x] `.claude/commands/review/review-diff.md` (versioned prompt, `{diff}` placeholder)

### Integration
- [x] `src/review/cli.py` (argparse `--diff`/`--model`; frontmatter strip; `.replace("{diff}", …)`; clean exit-1 on every failure)
- [x] `fixtures/pr-01/sample.diff` (seeded `if match == None:` bug on a list)
- [x] `Makefile` (`ci-review`, `test`, `test-unit`, `test-integration`; `metrics`/`test-gen` stubs)

### Testing & validation
- [x] `tests/__init__.py`, `tests/conftest.py` (src/review on path, `load_env`, capability gate)
- [x] `tests/fixtures/sample_claude_output.json` (recorded golden output)
- [x] `tests/test_schema.py` (valid schema; enum + required enforcement; round-trip)
- [x] `tests/test_parse.py` (golden → finding; error envelope; fallback; malformed → ParseError)
- [x] `tests/test_post.py` (file:line mapping; structural only)
- [x] `tests/test_cli.py` (timeout/error-envelope/nonzero-rc/missing-file → clean exit-1)
- [x] `tests/test_runner_live.py` [integration] (real `claude -p`, haiku, no hang)

### Validation results
- [x] Level 1 — `py_compile` on all modules: **clean**
- [x] Level 2 — offline unit suite (`-m "not integration"`): **19 passed, 2 deselected**
- [x] Level 3 — integration (`-m integration`, haiku): **2 passed in ~19.5s**
- [x] Level 4 — `make ci-review PR=fixtures/pr-01/sample.diff < /dev/null`:
      **exit 0**, 1 finding at `src/notify.py:7` (seeded bug caught), no hang
- [x] No `claude-agent-sdk` / `anthropic` / `gh` imports (verified via grep)

## Review

**What worked**
- The pre-verified CLI contract in the plan (result element → `structured_output`
  primary, `result` string fallback; stdout/stderr separation) was accurate — the
  parser worked first try against both the golden fixture and the live CLI.
- Splitting schema-drives-both-sides (one `FINDINGS_SCHEMA` feeds `--json-schema`
  and post-hoc validation) means the CLI contract and parser cannot drift.
- The seeded fixture bug was flagged with a correct, specific finding at the right
  new-file line — the `file:line` mapping gate holds end-to-end.

**What didn't (and the fix)**
- The integration test's `from conftest import claude_runnable` failed at
  collection (`conftest` isn't importable by name). Fixed by inlining the
  capability check with `shutil.which("claude")` in the test's `pytestmark`.
- `make` emits harmless `xcrun_db` cache-write warnings under the sandbox; the
  recipe still runs and exits 0. Cosmetic only.

**Deviations from the plan**
- Added `tests/test_cli.py` (not in the plan's file list) to cover the CLI-level
  edge cases the plan's Testing Strategy explicitly required (timeout → exit-1,
  error envelope → exit-1) without shelling out.
- Added a minimal `.gitignore` (`__pycache__`, `.pytest_cache`) for hygiene.

**Next**: Phase 2 — Precision (`.agents/plans/phase-2-precision.md`).

## Phase 2 — Precision (TR3 / TR4 / TR5)

Plan: `.agents/plans/phase-2-precision.md`
Goal: turn the Phase-1 spine into a *precise* reviewer — seeded ground-truth
fixture, CLAUDE.md as the runtime context channel (TR3), enriched prompt
(TR4/TR5), and a precision/recall harness with a demonstrable TR3 delta.

### Foundation
- [x] Verify Phase-1 interfaces present & green (offline 19 passed; `Finding`
      fields + `invoke_claude` signature match the plan)
- [x] TR3 auto-load live probe (platypus): `CLAUDE.md` in cwd changes the answer
- [x] `config.py` — `BASELINE_MODEL`, `FIXTURE_REPO`, `GROUND_TRUTH`,
      `BASELINE_PROMPT`, `ENRICHED_PROMPT`, `METRICS_DIR`, `LINE_MATCH_TOLERANCE`
- [x] `severity.py` — `normalize_severity`, `PATTERN_SEVERITY` override,
      `canonical_severity`, `apply_canonical_severity`, `sort_by_severity` (pure)
- [x] `workspace.py` — `stage_workspace`/`staged`/`cleanup_workspace` (TR3
      isolation under `$TMPDIR`; excludes `ground_truth.json`, `*.diff`,
      `__pycache__`; temp-dir footgun guard)

### Fixture & prompt (ground truth + the lever)
- [x] `fixtures/sample-repo/src/orders.py` — REAL bug (None-deref, must flag)
- [x] `fixtures/sample-repo/src/settings.py` — convention-dependent (broad
      `except` by policy, must NOT flag when CLAUDE.md present) — the TR3 lever
- [x] `fixtures/sample-repo/src/{ingest,summary}.py` — cross-file key mismatch
- [x] `pr.diff` (all four files) + `pr-02.diff` (re-introduces None-deref class)
- [x] `ground_truth.json` (answer key; cross-file case accepts producer OR
      consumer location)
- [x] `fixtures/sample-repo/CLAUDE.md` — runtime context (settings-total policy);
      convention lives ONLY here, never in the source files
- [x] `review-diff.baseline.md` (verbatim P1 snapshot) + enriched `review-diff.md`
      (explicit flag/don't-flag + few-shot + severity rubric w/ examples)

### Scoring & integration
- [x] `runner.py` — added optional `cwd` (backward-compatible; the TR3 lever)
- [x] `metrics.py` — pure scorer (`score`/`match`/`format_report`) + live driver
      (`run_variant`/`run_metrics`/`run_tr3_demo`)
- [x] `cli.py` — `--prompt {enriched,baseline}`, `--repo`, canonical severity +
      sort before emit (P1 default behavior preserved)
- [x] `Makefile` — `metrics` + `tr3-demo` targets

### Testing & validation
- [x] `test_severity.py` (offline) — aliases, pattern override, no-mutation, sort
- [x] `test_metrics.py` (offline) — TP/FP/FN, precision/recall/F1, integration
      exclusion, bonus (known-gap) scoring, multi-location, tolerance, suffix path
- [x] `test_workspace.py` (offline) — includes CLAUDE.md, excludes answer key,
      under `$TMPDIR`, cleanup refuses non-temp
- [x] `test_precision_live.py` [integration] — 5 acceptance demos

### Validation results
- [x] Level 1 — `py_compile` all modules/tests/fixtures: **clean**
- [x] Level 2 — offline suite (`-m "not integration"`): **53 passed, 7 deselected**
- [x] Level 3 — integration (`-m integration`, haiku): **5 passed in ~4.5 min**
- [x] Level 4 — `make metrics` + `make tr3-demo`: deltas produced (below)
- [x] Level 5 — `make ci-review PR=fixtures/pr-01/sample.diff` (haiku): **exit 0**,
      seeded bug flagged, canonical severity applied — P1 preserved
- [x] No `anthropic` / `claude-agent-sdk` / `gh` imports (grep clean)

## Review — Phase 2

**Headline numbers (fixture ground truth, haiku tier):**
- Precision/recall A/B (baseline vs enriched prompt, CLAUDE.md present in both):
  **baseline 1.00 / enriched 1.00** (precision & recall). Enriched ≥ baseline
  gate holds. On a conservative model the baseline is already precise *when it
  has project context*, so the prompt A/B shows parity, not a jump.
- **TR3 present-vs-absent delta (the vivid result):** the broad-`except` case is
  **flagged with CLAUDE.md ABSENT, not flagged with it PRESENT** →
  `behavior_changed: true`. This is where the precision engineering shows: the
  project policy in CLAUDE.md is what turns a real-looking FP into a non-finding.
- Severity **identical** for the None-deref class across `pr.diff` and
  `pr-02.diff` (guaranteed by `apply_canonical_severity`).

**What worked**
- Schema-drives-both-sides + the pure/offline scorer meant `test_metrics.py`
  could prove the metric correct before any live number was trusted.
- Staging under `$TMPDIR` cleanly isolated the TR3 A/B — the platypus probe
  confirmed the mechanism up front and de-risked the whole phase.
- The canonical `PATTERN_SEVERITY` backstop made severity consistency
  deterministic instead of hoping the model is stable.

**What didn't (and the fixes) — fixture/scorer calibration, per the plan's warning**
- *The pct-as-fraction lever was dead on haiku.* The model would not infer a
  percent/fraction unit bug even absent the convention (and my first draft leaked
  the convention in the source docstrings). Replaced it with a **broad-`except`
  settings reader**, which haiku reliably flags, exonerated by a CLAUDE.md policy.
- *The enriched prompt suppressed the TR3 signal.* Being deliberately
  conservative, it declined the broad-`except` in BOTH arms — nothing for
  CLAUDE.md to change. Fix: the TR3 demo holds the **baseline** prompt constant
  (it surfaces the borderline finding, so CLAUDE.md's suppression is observable).
- *A "false positive" that was really a scorer gap.* The model reported the
  cross-file bug at the producer (`ingest.py`) while ground truth pinned the
  consumer (`summary.py`), so it scored as an FP and tanked enriched precision.
  Fix: the cross-file case accepts **either** location, and a known-gap match is
  scored as a **bonus, never an FP**.

**Deviation from the plan (documented)**
- The plan assumed a single pass would MISS the cross-file bug. Empirically, a
  *whole-diff* single pass has cross-file visibility and a capable model can catch
  it. Per-file *isolation* (Phase-3 TR6) is what genuinely can't. So the
  cross-file case is a **known gap** (excluded from single-pass recall, catching
  it is precision-neutral), and the live test records the catch rather than
  asserting a flaky "must miss."

**Next**: Phase 3 — Scale + Dedupe (multi-pass TR6/TR7, dedupe TR8, test-gen FR2).
