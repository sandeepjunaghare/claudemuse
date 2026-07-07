# Feature: Phase 1 — Headless + Structured

The following plan should be complete, but it's important that you validate documentation and codebase
patterns and task sanity before you start implementing. Pay special attention to naming of existing utils,
types, and models. Import from the right files.

> **Ground-truth already established (do not re-derive):** the `claude` CLI contract in §CONTEXT was verified
> live against Claude Code **2.1.193** during planning. The probe commands and their exact outputs are
> reproduced below — trust them, but a single re-run is cheap if you want to reconfirm before coding.

## Feature Description

Stand up the **plumbing spine** of the CI review bot: invoke Claude Code **headlessly** (`claude -p`) with a
**JSON-Schema-constrained** output contract, capture its stdout, parse the event stream into validated
`Finding` objects, and **emit** them as inline-comment-shaped output mapped to `file:line`. This is Phase 1 of
the PIV build order (`docs/04-claude-code-ci-review-bot.md` §"Build phases", `PRD.md` §12). It deliberately does
**not** yet address precision (Phase 2), scale/dedupe (Phase 3), or the trust loop (Phase 4). The goal is a
`make ci-review PR=<diff>` pipeline that **exits cleanly, parses 100% against the schema, and maps every finding
to a real `file:line`**.

## User Story

As a **wary senior engineer wiring Claude Code into CI**,
I want to **run a PR-diff review non-interactively and get machine-parseable, schema-valid findings mapped to
file:line**,
So that **the pipeline never hangs and I can render findings as inline comments programmatically** (no prose
scraping).

## Problem Statement

There is no code yet — only spec + PRD. Before any precision engineering can be measured, we need a proven,
non-interactive invocation path whose output is a **contract, not prose**. The central technical risk was
whether `claude -p` even supports schema-constrained output and what shape it returns; both are now resolved
(see §CONTEXT). Remaining work is disciplined glue.

## Solution Statement

A thin **Python 3.10** layer in `src/review/`:
`config.py` (env + constants) → `schema.py` (canonical JSON Schema + validation) → `runner.py` (`subprocess`
call to `claude -p --output-format json --json-schema`) → `parse.py` (`Finding`/`Location` dataclasses +
stdout-array parsing) → `post.py` (format/emit) → `cli.py` (`make ci-review` entrypoint). The **prompt template**
is versioned at `.claude/commands/review/review-diff.md` (not inlined in code/YAML — TR-alignment). Offline unit
tests cover schema/parse/post using a **recorded golden output**; one `integration`-marked test shells out to
the real CLI and asserts no-hang + schema validity.

## Feature Metadata

**Feature Type**: New Capability (greenfield scaffold + first vertical slice)
**Estimated Complexity**: Medium (low algorithmic complexity; the risk was the CLI contract, now de-risked)
**Primary Systems Affected**: `src/review/*` (new), `.claude/commands/review/` (new), `fixtures/` (new),
`tests/` (new), `Makefile`/`requirements.txt`/`pytest.ini` (new)
**Dependencies**: `jsonschema` (**already installed**, 4.26.0), `python-dotenv` (**already installed**, 1.2.2),
`pytest` (**already installed**, 9.1.1). The **Claude Code CLI** (2.1.193, on PATH) is the agent under test.
No new packages required.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**This repo (contracts — non-negotiable):**
- `PRD.md` (§6 directory structure, §10 finding schema lines 280–314, §12 Phase 1 lines 344–351) — Why: the
  canonical finding schema and the file layout you must mirror.
- `docs/04-claude-code-ci-review-bot.md` (TR1 line 37, TR2 lines 38–40, build phase 1 line 67, acceptance lines
  78–84) — Why: the non-negotiable requirements this phase satisfies.
- `CLAUDE.md` (this repo) — Why: the **two-CLAUDE.md** rule and "CLI-as-agent, not SDK" rule. Do **not** import
  `claude-agent-sdk` or `anthropic` here even though they're installed — this project shells out to `claude -p`.

**Sibling house-style references** (Python monorepo conventions — mirror these exactly):
- `../multi-agent-research-agent/src/config.py` (lines 1–60) — Why: `.env`-at-monorepo-root loading via
  `Path(__file__).resolve().parents[N]`, module-level constants with rich docstrings, `load_env()` idempotency
  flag. **GOTCHA:** their file is `src/config.py` (parents[3]); ours is `src/review/config.py` — **one level
  deeper → parents[4]**. Count carefully.
- `../multi-agent-research-agent/src/schemas.py` (lines 1–55) — Why: **dataclass** data contracts, docstring
  style, "SDK-free so it unit-tests without credentials" philosophy → ours must be **subprocess-free** so parse
  tests run offline.
- `../multi-agent-research-agent/tests/conftest.py` (whole file) — Why: the `sys.path.insert(0, src)` +
  flat-absolute-import pattern (`import config`, `from parse import ...`), `load_env()` at collection, and the
  `agent_runnable()` / `shutil.which("claude")` capability gate for integration tests. Mirror this precisely.
- `../multi-agent-research-agent/pytest.ini` — Why: `testpaths = tests` + `integration` marker. **Drop
  `asyncio_mode = auto`** — this project is synchronous (`subprocess`, not async SDK).
- `../multi-agent-research-agent/requirements.txt` — Why: one-dep-per-line style. Ours differs: **no
  `claude-agent-sdk`, no `pytest-asyncio`**; add `jsonschema`.

### New Files to Create

```
claude-code-ci-review-bot/
├── Makefile                                  # make ci-review / test / test-unit / test-integration / install
├── requirements.txt                          # pytest, python-dotenv, jsonschema
├── pytest.ini                                # testpaths=tests, integration marker (NO asyncio)
├── .claude/commands/review/review-diff.md    # versioned prompt template (minimal in P1; enriched in P2)
├── src/
│   └── review/
│       ├── __init__.py                        # empty package marker
│       ├── config.py                          # env load + REVIEW_MODEL, CLAUDE_TIMEOUT_S, path constants
│       ├── schema.py                          # canonical findings JSON Schema dict + as_json_string + validate
│       ├── runner.py                          # subprocess.run(claude -p ...) -> RunResult(stdout,stderr,rc)
│       ├── parse.py                           # Location/Finding dataclasses + parse_result(stdout) -> ParsedReview
│       ├── post.py                            # format_comment(finding) + emit(findings) -> stdout
│       └── cli.py                             # argparse entrypoint for `make ci-review`
├── fixtures/
│   └── pr-01/
│       └── sample.diff                        # minimal seeded diff (one obvious bug) — the P1 harness
├── tests/
│   ├── __init__.py
│   ├── conftest.py                            # src on path, load_env, claude_runnable() gate
│   ├── fixtures/
│   │   └── sample_claude_output.json          # recorded golden CLI stdout for OFFLINE parse tests
│   ├── test_schema.py                         # schema is valid; good finding passes / bad fails
│   ├── test_parse.py                          # golden-output -> findings; error-envelope handling
│   ├── test_post.py                           # format_comment/emit output structure (file:line mapping)
│   └── test_runner_live.py                    # [integration] real claude -p on fixtures/pr-01
├── _tasks/todo.md                             # checklist per global instructions
└── .agents/plans/phase-1-headless-structured.md   # (this file)
```

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Claude Code Headless mode](https://code.claude.com/docs/en/headless) — Why: authoritative `-p` /
  `--output-format` / `--json-schema` reference. **However, the live probe below supersedes any doc ambiguity.**
- No external library docs needed — `jsonschema` and `subprocess` usage is standard and shown inline below.

### VERIFIED CLI CONTRACT (the crux — this is what `parse.py` is built around)

**Probe command** (reproducible; `ANTHROPIC_API_KEY` is at monorepo-root `.env`):
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
SCHEMA='{"type":"object","required":["findings"],"properties":{"findings":{"type":"array","items":{"type":"object","required":["file","line","issue"],"properties":{"file":{"type":"string"},"line":{"type":"integer"},"issue":{"type":"string"}}}}},"additionalProperties":false}'
claude -p "Review this diff. In file foo.py line 10, 'x == None' should be 'x is None'. Report it as one finding." \
  --output-format json --json-schema "$SCHEMA" --model claude-haiku-4-5-20251001 \
  >out.json 2>err.txt
```

**Verified facts (Claude Code 2.1.193):**
1. **`--json-schema <schema>` exists** and works only with `--print`/`-p`. It forces the model to call an
   internal **`StructuredOutput`** tool whose input schema *is* your schema. **Your top-level schema MUST be a
   JSON object** (the probe's `{"findings":[...]}` shape works; a bare array would not).
2. **`--output-format json` prints a JSON _array_ of event objects to STDOUT** (system init, thinking,
   assistant, user tool_result, and a final `result`). It is **not** a single object. Parse = `json.loads` →
   iterate → take the element with `type == "result"`.
3. The `result` element exposes the payload **two ways**:
   - `result["structured_output"]` → **already-parsed dict** (USE THIS as primary path), e.g.
     `{"findings":[{"file":"foo.py","line":10,"issue":"..."}]}`
   - `result["result"]` → the **same data as a JSON string** (fallback: `json.loads` it if
     `structured_output` is ever absent).
4. Success signals on the `result` element: `is_error == false`, `subtype == "success"`,
   `terminal_reason == "completed"`, `stop_reason == "tool_use"`. Process **exit code 0**.
5. **STDOUT is pure JSON**; the line `⚠ claude.ai connectors are disabled ...` goes to **STDERR**. → In
   `subprocess.run`, capture stdout and stderr **separately** and `json.loads(stdout)` only. Never merge.
6. Cost/latency note: a fresh invocation caches a ~27k-token system prompt (`cache_creation_input_tokens`).
   Expect ~$0.03 + a few seconds even for a trivial haiku call. Use haiku for integration tests to keep cost low.

**Recorded golden `result` element** (trim of the real probe output — this is the shape to hand-author into
`tests/fixtures/sample_claude_output.json`; keep it a valid array with at least the `result` element):
```json
[
  {"type": "system", "subtype": "init", "session_id": "golden", "model": "claude-haiku-4-5-20251001"},
  {"type": "result", "subtype": "success", "is_error": false, "stop_reason": "tool_use",
   "terminal_reason": "completed",
   "result": "{\"findings\":[{\"location\":{\"file\":\"src/auth.py\",\"line\":42},\"issue\":\"Token compared with == allows timing attack\",\"severity\":\"high\",\"suggested_fix\":\"Use hmac.compare_digest\",\"detected_pattern\":\"timing-unsafe-comparison\",\"category\":\"security\"}]}",
   "structured_output": {"findings": [
     {"location": {"file": "src/auth.py", "line": 42},
      "issue": "Token compared with == allows timing attack",
      "severity": "high",
      "suggested_fix": "Use hmac.compare_digest",
      "detected_pattern": "timing-unsafe-comparison",
      "category": "security"}
   ]}}
]
```
> Also record an **error-envelope** golden inline in the test (an array whose `result` element has
> `is_error: true`, `subtype: "error_during_execution"`) to test the failure path — no live call needed.

### Patterns to Follow

**Naming (Python — snake_case, matching siblings; the global camelCase rule is JS-specific and does not apply):**
functions/vars `snake_case`, dataclasses/types `PascalCase`, module constants `UPPER_SNAKE`.

**Config/env loading (mirror `../multi-agent-research-agent/src/config.py`):**
```python
# src/review/config.py  — NOTE parents[4] (one deeper than the sibling's parents[3])
from pathlib import Path
from dotenv import load_dotenv
# src/review/config.py -> review -> src -> project -> projects -> claudemuse(root)
_WORKSPACE_ENV = Path(__file__).resolve().parents[4] / ".env"
_loaded = False
def load_env() -> None:
    global _loaded
    if not _loaded:
        load_dotenv(_WORKSPACE_ENV)
        _loaded = True
```

**Dataclass contracts (mirror `../multi-agent-research-agent/src/schemas.py` — subprocess-free, docstringed):**
```python
from dataclasses import dataclass
@dataclass
class Location:
    file: str
    line: int
```

**Test path/import setup (mirror `../multi-agent-research-agent/tests/conftest.py`):**
```python
import shutil, sys
from pathlib import Path
_SRC = Path(__file__).resolve().parents[1] / "src" / "review"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
import config  # noqa: E402
config.load_env()
def claude_runnable() -> bool:
    return shutil.which("claude") is not None
```
> **GOTCHA:** siblings put `src/` on the path (their modules live directly in `src/`). Ours live in
> `src/review/`, so put **`src/review`** on the path → flat imports `import config`, `from parse import Finding`.
> Keep `cli.py` runnable via `PYTHONPATH=src/review` (the Makefile sets this).

**Subprocess invocation (`runner.py`) — the no-hang guarantee (TR1):**
```python
import subprocess
def invoke_claude(prompt: str, schema_json: str, model: str, timeout_s: int) -> "RunResult":
    proc = subprocess.run(
        ["claude", "-p", prompt,
         "--output-format", "json",
         "--json-schema", schema_json,
         "--model", model],
        capture_output=True, text=True, timeout=timeout_s,  # timeout = the hang backstop
        # NOTE: do NOT pass stdin=PIPE open; -p is non-interactive by construction.
    )
    return RunResult(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)
```
> **GOTCHA:** `subprocess.TimeoutExpired` is the only realistic "hang" — catch it and surface a clean pipeline
> failure with the partial output preserved (TR1 / PRD Risk #1). Never swallow it silently.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
Scaffold the project skeleton and the schema contract before any I/O.
**Tasks:** `requirements.txt`, `pytest.ini`, `Makefile`, `src/review/__init__.py`, `config.py`, `schema.py`.

### Phase 2: Core Implementation
The invoke → parse → emit vertical slice.
**Tasks:** `runner.py`, `parse.py` (dataclasses + `parse_result`), `post.py`, `.claude/commands/review/review-diff.md`.

### Phase 3: Integration
Wire the entrypoint and the fixture harness.
**Tasks:** `cli.py`, `fixtures/pr-01/sample.diff`, Makefile `ci-review` target end-to-end.

### Phase 4: Testing & Validation
Offline unit suite + one live integration test + record the golden fixture.
**Tasks:** `tests/conftest.py`, `tests/fixtures/sample_claude_output.json`, `test_schema.py`, `test_parse.py`,
`test_post.py`, `test_runner_live.py`, `_tasks/todo.md` review section.

---

## STEP-BY-STEP TASKS

Execute in order, top to bottom. Each task is atomic and independently testable.

### CREATE `requirements.txt`
- **IMPLEMENT**: three lines — `pytest`, `python-dotenv`, `jsonschema`. **No** `claude-agent-sdk`, **no**
  `anthropic`, **no** `pytest-asyncio` (this is a CLI-driver, not an SDK app; sync not async).
- **PATTERN**: `../multi-agent-research-agent/requirements.txt` (one dep per line).
- **GOTCHA**: all three are already installed in the shared venv — this file documents intent, no install needed.
- **VALIDATE**: `test -f requirements.txt && cat requirements.txt`

### CREATE `pytest.ini`
- **IMPLEMENT**:
  ```ini
  [pytest]
  testpaths = tests
  markers =
      integration: tests that shell out to the real `claude -p` CLI (needs CLI on PATH + credentials)
  ```
- **PATTERN**: `../multi-agent-research-agent/pytest.ini` — but **omit `asyncio_mode`** (no async here).
- **VALIDATE**: `../../.venv/bin/python -m pytest --collect-only -q 2>&1 | tail -5` (0 collected is fine now)

### CREATE `src/review/__init__.py`
- **IMPLEMENT**: empty file (package marker).
- **VALIDATE**: `test -f src/review/__init__.py`

### CREATE `src/review/config.py`
- **IMPLEMENT**: `load_env()` (idempotent, `.env` at `parents[4]`); constants:
  `REVIEW_MODEL = "claude-sonnet-4-6"` (production default; overridable), `CLAUDE_TIMEOUT_S = 300`,
  `PROMPT_TEMPLATE = Path(__file__).resolve().parents[2] / ".claude/commands/review/review-diff.md"`,
  `anthropic_key_present() -> bool` (checks `os.environ.get("ANTHROPIC_API_KEY")`).
- **PATTERN**: `../multi-agent-research-agent/src/config.py:1-60`.
- **IMPORTS**: `os`, `from pathlib import Path`, `from dotenv import load_dotenv`.
- **GOTCHA**: `parents[4]` for `.env` (deeper than sibling); `parents[2]` = project root for the prompt path.
  Add a one-line comment showing the walk so the count is auditable.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import config; config.load_env(); print(config.REVIEW_MODEL, config._WORKSPACE_ENV.exists())"`
  → expect `claude-sonnet-4-6 True`

### CREATE `src/review/schema.py`
- **IMPLEMENT**: `FINDINGS_SCHEMA` (a `dict`) — the canonical contract from `PRD.md:280-298`, wrapped as the
  **top-level object** `{"type":"object","required":["findings"],"properties":{"findings":{"type":"array",
  "items": <finding>}},"additionalProperties":false}` where `<finding>` requires
  `location{file:string,line:integer}`, `issue`, `severity` (enum critical/high/medium/low), `suggested_fix`,
  `detected_pattern`, `category` (all strings). Add `as_json_string() -> str` (`json.dumps(FINDINGS_SCHEMA)`)
  for the `--json-schema` flag, and `validate_findings_obj(obj) -> None` (raises `jsonschema.ValidationError`).
- **PATTERN**: `PRD.md:280-314` (finding schema + example). Full shape now (incl. `detected_pattern`,
  `category`) even though P1's prompt won't guide them well — this avoids reshaping in P2/P4 (sibling
  `schemas.py` "keep the full shape now" philosophy).
- **IMPORTS**: `json`, `import jsonschema`.
- **GOTCHA**: top-level MUST be `object` (verified: `--json-schema` maps to a tool input schema). A bare-array
  top level is rejected by the CLI.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import schema,json; jsonschema.__name__ if False else None; import jsonschema; jsonschema.Draft202012Validator.check_schema(schema.FINDINGS_SCHEMA); print('schema OK', len(schema.as_json_string()))"`

### CREATE `src/review/parse.py`
- **IMPLEMENT**:
  - Dataclasses `Location(file:str,line:int)` and
    `Finding(location:Location, issue:str, severity:str, suggested_fix:str, detected_pattern:str, category:str)`.
  - `@dataclass ParsedReview(findings:list[Finding], is_error:bool, terminal_reason:str|None, raw:list)`.
  - `parse_result(stdout:str) -> ParsedReview`:
    1. `events = json.loads(stdout)` (a list). If not a list or empty → raise `ParseError` (preserve `stdout`).
    2. `result_elem = next(e for e in events if e.get("type") == "result")` — if none → `ParseError`.
    3. If `result_elem.get("is_error")` → return `ParsedReview([], True, result_elem.get("terminal_reason"), events)`.
    4. `payload = result_elem.get("structured_output")`; if `None`, fallback `json.loads(result_elem["result"])`.
    5. `schema.validate_findings_obj(payload)` (belt-and-suspenders per TR2 — validate even though CLI enforced).
    6. Build `Finding`s from `payload["findings"]` (nested `location` → `Location`).
  - Define `class ParseError(Exception)`.
- **PATTERN**: dataclass style from `../multi-agent-research-agent/src/schemas.py`.
- **IMPORTS**: `json`, `from dataclasses import dataclass`, `import schema` (flat import).
- **GOTCHA**: parse **stdout only** (the connectors warning is on stderr). The events list has multiple
  `type=="assistant"` elements — you want `type=="result"`, not the last element blindly (though it happens to
  be last). Use the explicit `select` to be robust.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "import json,parse; d=open('tests/fixtures/sample_claude_output.json').read(); r=parse.parse_result(d); print(r.is_error, len(r.findings), r.findings[0].location.file, r.findings[0].location.line)"`
  → expect `False 1 src/auth.py 42` (run this AFTER the golden fixture task below)

### CREATE `src/review/post.py`
- **IMPLEMENT**: `format_comment(f:Finding) -> str` → e.g.
  `f"{f.location.file}:{f.location.line} [{f.severity}] {f.issue}\n    ↳ fix: {f.suggested_fix} (pattern={f.detected_pattern}, category={f.category})"`;
  `emit(findings:list[Finding]) -> None` prints a header (`N finding(s)`) then each formatted comment. Return
  nothing (Phase 1 = print/emit only; **no `gh` posting** — that's Phase 4 behind `--post`).
- **PATTERN**: plain stdout emit; keep the `(file, line)` pairing explicit — this is the "maps to real comment
  location" acceptance gate.
- **IMPORTS**: `from parse import Finding`.
- **GOTCHA**: do not import or reference `gh`/GitHub anything in Phase 1 (PRD Risk #6: emit-by-default; posting
  is opt-in and out of scope here).
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -c "from parse import Finding,Location; from post import format_comment; print(format_comment(Finding(Location('a.py',7),'boom','high','fix it','p','c')))"`

### CREATE `.claude/commands/review/review-diff.md`
- **IMPLEMENT**: a **minimal** review prompt template with a `{diff}` placeholder. Body (no heavy criteria yet —
  that's Phase 2/TR4): instruct the model to review the unified diff, report genuine issues, and — critically —
  emit findings **only** via the structured output (it will be forced to by `--json-schema`). Include the field
  meaning for `location.line` = the line number in the **new** file per the diff hunk headers.
  - Frontmatter: keep it minimal (`---\ndescription: Review a unified diff and emit structured findings\n---`).
- **PATTERN**: PRD §"review prompt lives in a versioned skill/command under `.claude/commands/`" (line 217).
- **GOTCHA**: `runner.py`/`cli.py` will read this file and **strip the YAML frontmatter** (everything between the
  first two `---` lines) before substituting `{diff}` and passing as the `-p` argument. Document this in a
  comment in `cli.py`. Do **not** rely on invoking it as a slash command (`claude -p "/review-diff"`) in P1 —
  the file is the versioned source of the prompt **text**; the runner composes the final prompt.
- **VALIDATE**: `test -f .claude/commands/review/review-diff.md && grep -q '{diff}' .claude/commands/review/review-diff.md && echo OK`

### CREATE `src/review/cli.py`
- **IMPLEMENT**: `argparse` with `--diff <path>` (required; the `PR=` value from the Makefile) and optional
  `--model` (default `config.REVIEW_MODEL`). Flow: `config.load_env()` → read diff file → read prompt template
  (`config.PROMPT_TEMPLATE`), strip frontmatter, `.format(diff=<diff text>)` (or `.replace("{diff}", diff)` to
  avoid brace-escaping issues in diffs) → `runner.invoke_claude(prompt, schema.as_json_string(), model,
  config.CLAUDE_TIMEOUT_S)` → on non-zero rc or empty stdout, print stderr + raw and `sys.exit(1)` →
  `parse.parse_result(stdout)` → if `is_error`, print terminal_reason + `sys.exit(1)` → `post.emit(findings)` →
  `sys.exit(0)`. Wrap the invoke in `try/except subprocess.TimeoutExpired` → print a clear timeout message +
  `sys.exit(1)`.
- **PATTERN**: entrypoint style like `../multi-agent-research-agent/run_example.py` (top-level runnable script).
- **IMPORTS**: `argparse`, `sys`, `re` (frontmatter strip), `subprocess` (for the TimeoutExpired type),
  `import config, schema, runner, parse, post`.
- **GOTCHA**: use `.replace("{diff}", diff)` NOT `str.format` — diffs contain `{`/`}` that break `format`.
- **VALIDATE**: `PYTHONPATH=src/review ../../.venv/bin/python -m cli --help` (argparse help prints, exit 0)

### CREATE `fixtures/pr-01/sample.diff`
- **IMPLEMENT**: a small unified diff (valid `git diff` format, with `+++ b/...` and `@@` hunk headers) seeding
  **one obvious, unambiguous bug** — e.g. a new function using `if x == None:` (should be `is None`), or an
  off-by-one. Keep it ~15 lines. This is the P1 harness only; the full precision fixture (real bug +
  idiomatic-unusual + cross-file) is **Phase 2**.
- **PATTERN**: PRD §12 Phase 1 "minimal fixture PR"; full harness deferred to `PRD.md:353-361`.
- **GOTCHA**: line numbers in the finding come from the diff's new-file hunk numbering — make the seeded bug's
  line obvious so the mapping is checkable.
- **VALIDATE**: `grep -qE '^@@' fixtures/pr-01/sample.diff && echo OK`

### CREATE `tests/__init__.py` and `tests/fixtures/sample_claude_output.json`
- **IMPLEMENT**: empty `tests/__init__.py`. For the golden JSON, hand-author the array from §CONTEXT "Recorded
  golden `result` element" (the `src/auth.py:42` example) — a valid JSON array with a `system/init` element and
  a `result` element containing both `structured_output` and `result`. **Optionally** regenerate it live to be
  faithful: run the probe command from §CONTEXT and copy stdout here (but the hand-authored version is
  sufficient and keeps tests hermetic).
- **VALIDATE**: `../../.venv/bin/python -c "import json; d=json.load(open('tests/fixtures/sample_claude_output.json')); print(type(d).__name__, [e['type'] for e in d])"`
  → expect `list ['system', 'result']`

### CREATE `tests/conftest.py`
- **IMPLEMENT**: put `src/review` on `sys.path`; `import config; config.load_env()`; define
  `claude_runnable()` (`shutil.which("claude") is not None`); add a `sample_output` fixture returning the golden
  JSON string, and a `project_root` fixture.
- **PATTERN**: `../multi-agent-research-agent/tests/conftest.py` (adjust path to `src/review`).
- **VALIDATE**: `../../.venv/bin/python -m pytest --collect-only -q 2>&1 | tail -3`

### CREATE `tests/test_schema.py`
- **IMPLEMENT**: (1) `schema.FINDINGS_SCHEMA` passes `Draft202012Validator.check_schema`; (2) a fully-valid
  findings object validates; (3) missing `severity` → `ValidationError`; (4) `severity:"blocker"` (not in enum)
  → `ValidationError`; (5) `as_json_string()` round-trips via `json.loads`.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_schema.py -q`

### CREATE `tests/test_parse.py`
- **IMPLEMENT**: (1) `parse_result(golden)` → 1 finding, `location.file=='src/auth.py'`, `line==42`,
  `severity=='high'`, `is_error is False`; (2) error-envelope array (`is_error:true`) → `ParsedReview` with
  `is_error True`, `findings==[]`, `terminal_reason` surfaced; (3) missing-`structured_output` array (only
  `result` string present) → still parses via fallback; (4) non-JSON stdout → `ParseError`; (5) array with no
  `result` element → `ParseError`.
- **PATTERN**: offline — uses only the golden fixture + inline arrays; **no `claude` call** (no `integration`
  marker).
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_parse.py -q`

### CREATE `tests/test_post.py`
- **IMPLEMENT**: `format_comment` contains `file:line`, the severity token, and the fix; `emit` (capture via
  `capsys`) prints one line per finding + a count header. Assert on **structure** (contains `a.py:7`,
  `[high]`), never exact prose.
- **VALIDATE**: `../../.venv/bin/python -m pytest tests/test_post.py -q`

### CREATE `tests/test_runner_live.py`  [integration]
- **IMPLEMENT**: `@pytest.mark.integration`, `@pytest.mark.skipif(not claude_runnable(), reason=...)`. Read
  `fixtures/pr-01/sample.diff`, build the prompt, call `runner.invoke_claude(..., model="claude-haiku-4-5-20251001",
  timeout_s=120)`, then `parse.parse_result(stdout)`. Assert: `returncode == 0`; `is_error is False`; **every**
  finding validates against the schema (already guaranteed by parse, but assert the count ≥ 0 and each has a
  real `location.file`/`line`); the call **completes within the timeout** (no `TimeoutExpired`). Use haiku to
  cap cost (~$0.03/run).
- **PATTERN**: capability gate + lazy structure from `../multi-agent-research-agent/tests/conftest.py`
  (`agent_runnable`).
- **GOTCHA**: this test costs money and needs the CLI — it must be **skipped** by default `not integration`
  runs. Do not assert on the model's wording (non-deterministic); assert on structure/exit/no-hang only.
- **VALIDATE**: `../../.venv/bin/python -m pytest -m integration tests/test_runner_live.py -q` (requires CLI + key)

### CREATE `Makefile`
- **IMPLEMENT**: variables `PY=../../.venv/bin/python`, `PYTHONPATH=src/review`. Targets:
  - `install:` → `$(PY) -m pip install -r requirements.txt`
  - `ci-review:` → `PYTHONPATH=src/review $(PY) -m cli --diff $(PR)` (usage: `make ci-review PR=fixtures/pr-01/sample.diff`)
  - `test:` / `test-unit:` → `$(PY) -m pytest -m "not integration" -q`
  - `test-integration:` → `$(PY) -m pytest -m integration -q`
  - `.PHONY` for all.
- **PATTERN**: PRD §10 Make targets (`make ci-review PR=<path>`). `test-gen`/`metrics` targets are **Phase
  2/3** — you may add them as stubs that echo "not implemented (Phase N)" but do not implement them.
- **GOTCHA**: Makefile recipes need **tabs**, not spaces. `PR` is passed as `make ci-review PR=...`.
- **VALIDATE**: `make -n ci-review PR=fixtures/pr-01/sample.diff` (dry-run prints the command)

### CREATE `_tasks/todo.md`
- **IMPLEMENT**: a checkable list mirroring these tasks (per global instructions), with a "Phase 1" heading.
  Mark items complete as you go; append a short review section at the end (what worked / what didn't).
- **VALIDATE**: `test -f _tasks/todo.md`

---

## TESTING STRATEGY

### Unit Tests (offline, default `-m "not integration"`)
- **Schema** (`test_schema.py`): the contract is a valid JSON Schema; enum + required enforcement.
- **Parse** (`test_parse.py`): golden-output → `Finding`s; error-envelope; `structured_output` fallback;
  malformed stdout → `ParseError`. Uses the recorded golden fixture — **no network, no CLI**.
- **Post** (`test_post.py`): `file:line` mapping present in emitted output; structural assertions only.
- Design tests with `capsys`/plain assertions; **never assert on model wording** (PRD principle 5).

### Integration Tests (`-m integration`, gated on `claude_runnable()`)
- **Runner-live** (`test_runner_live.py`): real `claude -p` on `fixtures/pr-01/sample.diff`; asserts clean exit,
  no `TimeoutExpired` (the no-hang gate, TR1), and 100% schema-valid parse (TR2). Haiku to cap cost.

### Edge Cases (must be covered)
- `subprocess.TimeoutExpired` → clean pipeline failure, not a hang (TR1). *(unit: monkeypatch `subprocess.run`
  to raise; assert `cli` exits 1 with a timeout message.)*
- CLI returns `is_error: true` envelope → surfaced, exit 1, raw preserved.
- Empty findings (`{"findings": []}`) → emit "0 findings", exit 0 (a clean PR is valid).
- stdout with the stderr warning accidentally merged → confirm parse reads stdout only (documented; the live
  test proves separation).
- Diff containing `{`/`}` characters → prompt composition via `.replace`, not `.format` (no KeyError).

---

## VALIDATION COMMANDS

Run from the project root (`.../projects/claude-code-ci-review-bot`). `PY=../../.venv/bin/python`.

### Level 1: Syntax & Style
```bash
../../.venv/bin/python -m py_compile src/review/*.py tests/*.py
# (no ruff/black installed in the shared venv — py_compile is the syntax gate)
```

### Level 2: Unit Tests (offline — MUST pass with zero network/CLI)
```bash
../../.venv/bin/python -m pytest -m "not integration" -q
```

### Level 3: Integration Tests (needs `claude` CLI + ANTHROPIC_API_KEY)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
../../.venv/bin/python -m pytest -m integration -q
```

### Level 4: Manual Validation (the acceptance demo)
```bash
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-)
make ci-review PR=fixtures/pr-01/sample.diff
# EXPECT: prints N finding(s), each as `file:line [severity] issue ... fix`, exit code 0, no hang.
echo "exit: $?"
```

### Level 5: Additional Validation (optional)
```bash
# Prove non-interactivity end-to-end (no stdin): should still complete, never block.
make ci-review PR=fixtures/pr-01/sample.diff < /dev/null
```

---

## ACCEPTANCE CRITERIA

- [ ] `make ci-review PR=fixtures/pr-01/sample.diff` completes **non-interactively** and exits 0 (TR1; no hang).
- [ ] 100% of emitted findings are **valid JSON against `FINDINGS_SCHEMA`** and map to a real `file:line` (TR2).
- [ ] Parsing reads **stdout only**; the stderr connectors warning never corrupts parsing.
- [ ] `parse_result` handles success, `is_error`, `structured_output`-absent fallback, and malformed stdout.
- [ ] `subprocess.TimeoutExpired` surfaces as a clean exit-1 failure (proven by a unit test), not a hang.
- [ ] Offline unit suite (`-m "not integration"`) passes with **no network/CLI** dependency.
- [ ] The integration test passes when the CLI is available (skips cleanly otherwise).
- [ ] The review prompt lives in `.claude/commands/review/review-diff.md`, **not** inlined in code/YAML.
- [ ] No `claude-agent-sdk` / `anthropic` / `gh` imports (CLI-as-agent; posting is out of P1 scope).

## COMPLETION CHECKLIST
- [ ] All tasks completed in order; each task's `VALIDATE` command passed immediately.
- [ ] Level 1–4 validation commands executed successfully.
- [ ] Offline unit suite green; integration test green (or cleanly skipped).
- [ ] `_tasks/todo.md` updated with a completion review.
- [ ] No linting/type errors (py_compile clean).
- [ ] Manual `make ci-review` demo confirms findings map to `file:line`.

---

## NOTES

**Decisions made during planning (with rationale):**
1. **`jsonschema`, not Pydantic** (resolves PRD assumption #4). The same schema `dict` feeds both the
   `--json-schema` CLI flag (serialized) and post-hoc validation → **one source of truth**. Pydantic would
   force maintaining the shape twice. `jsonschema` is already installed. (Pydantic is also installed and could
   be adopted later without churn if model-class ergonomics are wanted.)
2. **Inline the diff into the `-p` prompt** (no tools granted). Deterministic, zero tool-permission/hang risk,
   and matches P1 scope ("parse and print findings"). Letting the model `Read` files from the repo is a
   possible Phase 2/3 optimization, not needed now.
3. **Full canonical schema shape from day 1** (incl. `detected_pattern`, `category`) even though P1's minimal
   prompt won't populate them meaningfully. Avoids reshaping the contract in P2/P4 (sibling `schemas.py`
   philosophy). They're required, so the CLI will force *some* value; P2/P4 make them *good*.
4. **Model default `claude-sonnet-4-6`** for production reviews; **integration tests override to
   `claude-haiku-4-5-20251001`** to cap cost. The CLI's own default is Opus; we set an explicit constant so cost
   is predictable and reproducible (mirrors sibling model-tier constants).
5. **Prompt template read + frontmatter-stripped by the runner** rather than invoked as a slash command. Keeps
   the prompt versioned/team-shared (TR-aligned) while letting the runner compose `template + diff` cleanly.

**Environment gotchas confirmed during planning:**
- Shared venv is Python **3.10.2** at `../../.venv`; `jsonschema/pytest/python-dotenv` **already installed** →
  `make install` is a formality.
- `ANTHROPIC_API_KEY` is at **monorepo-root `.env`** (`parents[4]` from `src/review/config.py`).
- **`gh` auth is currently broken** ("token in keyring is invalid") — irrelevant to Phase 1 (no posting) but
  will need `gh auth login` before Phase 4's `--post`.
- No `ruff`/`black` in the venv → Level 1 is `py_compile` only.

**Out of scope for Phase 1 (do not build):** precision criteria/few-shot/severity rubric (P2), fixture
CLAUDE.md / TR3 behavior change (P2), multi-pass/independent-instance (P3), dedupe (P3), test-gen (P3),
`detected_pattern` instrumentation/quarantine (P4), real `gh --post` (P4).
