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
