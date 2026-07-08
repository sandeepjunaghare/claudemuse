# PRD — Claude Code CI/CD Review & Test Bot

> **Project 04** · Maps to official **Exam Scenario 5** · Domains **D3** (Claude Code Config & Workflows) + **D4** (Prompt Engineering & Structured Output)
> **Status:** Greenfield — spec + guidance only, no code yet.
> **Effort:** 2–3 days · **Difficulty:** ●●○

---

## 1. Executive Summary

Engineering teams want automated PR review and test generation they *actually trust*. Most bots fail not on capability but on **trust**: a reviewer that emits noise gets muted, and one noisy category poisons confidence in every other finding. This project wires **Claude Code in headless mode** (`claude -p`) into a CI pipeline that reviews pull-request diffs and generates tests, emitting **structured, schema-validated** findings that map to inline PR comments.

The system is deliberately **not an SDK application**. The "agent" is the **Claude Code CLI itself**, invoked non-interactively from a pipeline step. A thin **Python 3.10** glue layer parses its JSON output against a fixed schema, deduplicates against prior runs, normalizes severity, and either prints comments (default) or posts them via `gh` (behind an integration flag). Project context — review criteria, testing standards, severity definitions — reaches the run through the **reviewed project's CLAUDE.md**, never hand-pasted into the prompt string.

The MVP's headline deliverable is a **trust metric**: precision/recall measured on a seeded fixture repo, before vs. after the precision-engineering work (explicit criteria + few-shot + severity examples). Success is not "the bot finds bugs" — it is "the bot flags the genuine bug, stays silent on the idiomatic-but-unusual pattern, labels severity identically across PRs, and posts zero duplicates on re-runs."

**MVP goal statement:** *A locally-runnable `make ci-review` pipeline that reviews a fixture PR headlessly, produces 100%-schema-valid findings mapped to real file:line locations, demonstrably suppresses false positives and duplicates, and reports a precision/recall number as ground-truth proof of trust.*

---

## 2. Mission

**Mission:** Make automated code review a trusted teammate rather than muted noise, by treating structured output as a contract and false-positive suppression as the primary engineering objective.

**Core principles:**

1. **Trust is the product.** Every design choice optimizes for developers *acting on* findings. One noisy category is an existential threat, not a minor bug.
2. **Structure is the contract.** Findings are JSON validated against a schema — never scraped from prose. If it doesn't parse, it doesn't post.
3. **Headless or bust.** The pipeline never blocks on input. A run that can hang on a prompt is an automatic failure.
4. **Independence beats introspection.** A fresh review instance without the generator's reasoning context beats self-review or extended thinking.
5. **Validation is structural, never editorial.** The fixture repo is ground truth. Assert on outcomes and structure, never on the model's wording.

---

## 3. Target Users

### Primary persona — "The wary senior engineer"
- **Who:** Reviews PRs daily, has been burned by noisy linters and low-signal bots.
- **Technical comfort:** High. Reads CI logs, edits CLAUDE.md, tunes prompts.
- **Needs:** High-precision findings; consistent severity; no comment spam on re-pushes; the ability to *disable a noisy category* without losing the good ones.
- **Pain points:** Bots that flag idiomatic code as bugs; duplicate comments across commits; inconsistent severity that makes triage impossible; opaque "trust me" outputs with no measurable precision.

### Secondary persona — "The team lead / bot owner"
- **Who:** Owns the shared review prompt and the CI configuration.
- **Needs:** A versioned, team-shared prompt (in `.claude/commands/`, not inlined in YAML); instrumentation to see *which patterns* generate dismissed findings; a lever to quarantine a bad category while refining it.
- **Pain points:** Prompt drift across the team; no feedback loop from dismissed findings to prompt improvements.

---

## 4. MVP Scope

### Core Functionality
- ✅ Headless review of a PR diff via `claude -p` (TR1, FR1)
- ✅ JSON-schema-constrained findings: `location`, `issue`, `severity`, `suggested_fix`, `detected_pattern` (TR2, TR9)
- ✅ Map findings to inline comment locations (file + line) (FR1)
- ✅ Test generation for changed code that skips already-covered cases (FR2)
- ✅ Explicit flag/don't-flag criteria + few-shot pairs in the review prompt (TR4)
- ✅ Severity definitions, each with a concrete code example (TR5)
- ✅ Multi-pass review: per-file local passes + separate cross-file integration pass (TR6)
- ✅ Independent review instance, separate from any generation context (TR7)
- ✅ Duplicate suppression across re-runs via prior-findings context (TR8, FR3)
- ✅ `detected_pattern` instrumentation + dismissed-finding tracking + **category quarantine** (TR9, FR4)

### Technical
- ✅ Python 3.10 glue in the shared monorepo venv
- ✅ Review prompt lives in a versioned skill/command under `.claude/commands/`
- ✅ Context supplied via the **reviewed project's CLAUDE.md** (TR3)
- ✅ `pytest` suite with an `integration` marker (unit tests run offline)
- ✅ Seeded **fixture repo** as the measurement harness

### Integration
- ✅ Local `make ci-review` pipeline runner (primary CI target)
- ✅ Emit structured comments by default; **optional** real `gh` PR-comment posting behind an integration flag
- ✅ `gh` CLI used for any GitHub interaction (per global instructions)

### Out of Scope (deferred)
- ❌ Real GitHub Actions workflow on a live sample repo *(stretch)*
- ❌ Always-on live posting to GitHub PRs on every run
- ❌ Hosted bot service / multi-tenant deployment
- ❌ Support for VCS other than Git/GitHub
- ❌ Replacing human review
- ❌ Weekly batch "tech-debt report" via the Batch API *(stretch)*
- ❌ Web dashboard of dismissed-finding patterns *(stretch; MVP tracks patterns in a file)*

---

## 5. User Stories

1. **As a wary engineer, I want** the bot to review my PR without ever hanging the CI job, **so that** the pipeline is reliable.
   *Example:* `make ci-review PR=fixtures/pr-01` returns a non-zero-free exit and structured output within the job, no prompt ever blocks.

2. **As a reviewer, I want** every finding to be machine-parseable JSON with a location, issue, severity, and fix, **so that** they render as precise inline comments.
   *Example:* A finding `{ "location": {"file":"auth.py","line":42}, "severity":"high", "issue":"...", "suggested_fix":"...", "detected_pattern":"null-deref" }` maps to a comment on `auth.py:42`.

3. **As a reviewer, I want** the bot to stay silent on idiomatic-but-unusual code, **so that** I trust the findings it does emit.
   *Example:* The fixture's deliberately-unusual-but-correct pattern produces **zero** findings; the seeded genuine bug produces exactly one.

4. **As a triager, I want** the same issue class to get the same severity across different PRs, **so that** I can prioritize consistently.
   *Example:* A null-deref labeled `high` in PR-01 is also `high` in PR-02.

5. **As an engineer re-pushing a fix, I want** no duplicate comments for issues already reported, **so that** the thread stays readable.
   *Example:* On the second commit, previously-reported-and-unchanged issues produce **zero** new comments; only new/unresolved issues appear.

6. **As a developer, I want** generated tests that don't duplicate existing coverage, **so that** I only see net-new tests.
   *Example:* Given existing tests for the happy path, test-gen proposes only the untested error-path cases.

7. **As a team lead, I want** to supply review criteria through the project's CLAUDE.md, **so that** the whole team shares one source of truth.
   *Example:* Running with the fixture's CLAUDE.md present changes findings vs. running without it (demonstrable TR3 behavior change).

8. **As a bot owner, I want** to quarantine a high-false-positive category, **so that** I can silence noise without losing good findings.
   *Example:* Disabling the `style-nit` category stops those comments while `null-deref` and cross-file findings still post.

### Technical user stories
9. **As a maintainer, I want** the parse/dedupe/severity logic unit-tested offline, **so that** CI doesn't require `claude -p` or GitHub for every test run.
10. **As a maintainer, I want** the review prompt versioned in `.claude/commands/`, **so that** prompt changes are reviewed like code.

---

## 6. Core Architecture & Patterns

### High-level flow
```
                    ┌─────────────────────────────────────────────┐
  PR diff  ─────▶   │  make ci-review  (local pipeline runner)     │
                    └─────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┼───────────────────────────────┐
        ▼                            ▼                                 ▼
  (TR6) per-file passes      (TR6) cross-file            (TR7) fresh review instance
  claude -p --json-schema    integration pass            (no generator context)
        │                            │
        └────────────┬───────────────┘
                     ▼
        ┌───────────────────────────────┐
        │  Python glue                    │
        │   • parse + schema-validate     │  (TR2)
        │   • dedupe vs prior findings    │  (TR8/FR3)
        │   • normalize severity          │  (TR5)
        │   • pattern instrumentation     │  (TR9)
        │   • quarantine filter           │  (TR9/FR4)
        └───────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   emit comments (default)   post via gh (--post flag)
                     │
                     ▼
        ┌───────────────────────────────┐
        │  fixture repo = ground truth    │
        │  precision / recall / dup-rate  │
        └───────────────────────────────┘
```

### Proposed directory structure
```
claude-code-ci-review-bot/
├── CLAUDE.md                       # guidance for developing THE BOT
├── PRD.md
├── Makefile                        # make ci-review / make test-gen / make metrics
├── requirements.txt
├── pytest.ini                      # testpaths=tests, integration marker
├── docs/04-claude-code-ci-review-bot.md
├── .claude/
│   └── commands/
│       ├── review/                 # versioned, team-shared review prompt (TR4/TR5)
│       └── test-gen/               # versioned test-generation prompt
├── src/
│   ├── review/
│   │   ├── schema.py               # JSON schema for findings (TR2/TR9)
│   │   ├── runner.py               # invokes claude -p headless (TR1)
│   │   ├── multipass.py            # per-file + integration orchestration (TR6)
│   │   ├── parse.py                # parse + validate findings (TR2)
│   │   ├── dedupe.py               # prior-findings suppression (TR8)
│   │   ├── severity.py             # normalization / consistency (TR5)
│   │   ├── instrument.py           # detected_pattern tracking + quarantine (TR9)
│   │   └── post.py                 # emit / gh posting (FR1)
│   └── testgen/
│       └── generate.py             # test-gen skipping covered cases (FR2/TR8)
├── fixtures/
│   └── sample-repo/                # THE measurement harness
│       ├── CLAUDE.md               # review criteria = bot's context channel (TR3)
│       ├── <real bug>              # must flag
│       ├── <idiomatic-unusual>     # must NOT flag
│       └── <cross-file bug>        # only integration pass catches it
├── data/
│   ├── prior_findings/             # per-PR history for dedupe (TR8)
│   └── dismissed_patterns.json     # feedback loop store (TR9)
├── tests/
└── _tasks/todo.md
```

### Key design patterns
- **CLI-as-agent.** No SDK. `subprocess` invokes `claude -p --output-format json --json-schema ...`; the glue owns everything else.
- **Schema-first.** A single canonical findings schema is the contract between the model and the pipeline. Parse failures are surfaced, never silently dropped.
- **Two-CLAUDE.md separation.** This repo's CLAUDE.md guides *bot development*; the fixture repo's CLAUDE.md is the bot's *runtime context channel* (TR3). They are never conflated.
- **Independent instance (TR7).** Review runs in a fresh `claude -p` invocation with no generation context — a process boundary, not a prompt instruction.
- **Multi-pass fan-out (TR6).** Large PRs split into per-file passes + one integration pass; results merged and deduped by the glue.
- **Offline-testable core.** Parse, dedupe, severity, and quarantine logic are pure functions over fixtures — unit-tested without shelling out.

---

## 7. Features

### Feature: Headless Review Runner (TR1, TR2, FR1)
- **Purpose:** Invoke Claude Code non-interactively and return schema-valid findings.
- **Operations:** build prompt from versioned command + diff → `subprocess` call to `claude -p --output-format json --json-schema <schema>` → capture stdout JSON.
- **Key features:** never blocks on input; timeout guard; non-zero exit surfaces as pipeline failure with the raw output preserved for debugging.

### Feature: Findings Schema & Parser (TR2, TR9)
- **Purpose:** Define and enforce the machine-readable contract.
- **Schema fields:** `location {file, line}`, `issue`, `severity ∈ {critical, high, medium, low}`, `suggested_fix`, `detected_pattern`, `category`.
- **Key features:** 100% of emitted findings validate; invalid findings are quarantined to an errors bucket, not posted; each finding maps to a real file:line in the diff.

### Feature: Precision Prompt (TR4, TR5)
- **Purpose:** The primary false-positive lever.
- **Operations:** explicit flag/don't-flag rules ("flag a comment only when claimed behavior contradicts the code"); few-shot pairs contrasting acceptable idiom vs. genuine bug; severity rubric where each level carries a concrete code example.
- **Key features:** versioned under `.claude/commands/`; changes are code-reviewed; drives the before/after precision-recall metric.

### Feature: Multi-Pass Orchestrator (TR6, TR7)
- **Purpose:** Handle large PRs without attention dilution; catch cross-file bugs.
- **Operations:** per-file local passes (parallelizable) + one cross-file integration pass; each pass a fresh independent instance.
- **Key features:** merges + dedupes per-file results; integration pass is the *only* one expected to catch the seeded cross-file data-flow bug.

### Feature: Duplicate Suppression (TR8, FR3)
- **Purpose:** Zero duplicate comments across re-runs.
- **Operations:** load prior findings for the PR → include in context → instruct Claude to report only new/still-unresolved issues; glue does a final structural dedupe by (file, line, pattern).
- **Key features:** second commit produces zero duplicates; resolved issues drop off.

### Feature: Test Generation (FR2, TR8)
- **Purpose:** Suggest net-new tests for changed code.
- **Operations:** supply existing tests as context so covered cases are skipped.
- **Key features:** no already-covered test is re-suggested.

### Feature: False-Positive Instrumentation & Quarantine (TR9, FR4)
- **Purpose:** Close the feedback loop; protect trust.
- **Operations:** every finding carries `detected_pattern`; dismissed findings tracked by pattern in `dismissed_patterns.json`; a category with a high dismissal rate can be **quarantined** (filtered out) via config.
- **Key features:** quarantining one category leaves all other categories emitting normally.

---

## 8. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Glue language | **Python 3.10** | Shared monorepo venv `../../.venv`; no per-project venv |
| Agent under test | **Claude Code CLI** (`claude -p`) | Must be on PATH; the "agent" is the CLI itself — **not** the Agent SDK or Messages API |
| GitHub interaction | **`gh` CLI** | Per global instructions; used for optional posting |
| Config / secrets | **python-dotenv** | `ANTHROPIC_API_KEY` from monorepo-root `.env` (two levels up) |
| Orchestration | **Makefile** | `make ci-review`, `make test-gen`, `make metrics` |
| Schema validation | **jsonschema** (or Pydantic) | Enforce the findings contract |
| Testing | **pytest** | `testpaths = tests`; `integration` marker gates `claude -p`/GitHub tests |
| Model | latest Claude (Opus/Sonnet 4.x) via the CLI's default | Model selection handled by Claude Code, not code |

**`requirements.txt` (initial):** `pytest`, `python-dotenv`, `jsonschema` (+ `pydantic` if chosen for schema modeling).

---

## 9. Security & Configuration

- **Auth:** `ANTHROPIC_API_KEY` loaded from monorepo-root `.env`; `gh` uses its own authenticated session. No secrets committed.
- **Configuration:** review criteria + severity rubric live in the **reviewed project's CLAUDE.md** (TR3) and the versioned `.claude/commands/` prompt. Quarantine config + dismissed patterns in `data/`.
- **Posting safety:** default mode **emits** comments (prints, mapped to file:line). Real `gh` posting is gated behind an explicit `--post` flag / integration marker — outward-facing action requires opt-in.
- **In scope:** non-interactive execution safety (no hangs); schema validation before any post; not posting invalid findings.
- **Out of scope:** hosted-service auth, multi-tenant secrets, rate-limit management for a fleet.
- **Deployment:** local pipeline runner for the MVP; GitHub Actions is a stretch goal.

---

## 10. Interface Specification

*(No HTTP API — this is a CLI/pipeline tool. Interface = Make targets + finding schema.)*

### Make targets
| Target | Purpose |
|---|---|
| `make ci-review PR=<path> [--post]` | Run headless multi-pass review; emit or post comments |
| `make test-gen PR=<path>` | Generate net-new tests skipping covered cases |
| `make metrics` | Compute precision/recall/dup-rate against the fixture repo |

### Finding schema (canonical contract)
```json
{
  "type": "object",
  "required": ["location", "issue", "severity", "suggested_fix", "detected_pattern", "category"],
  "properties": {
    "location": {
      "type": "object",
      "required": ["file", "line"],
      "properties": { "file": {"type": "string"}, "line": {"type": "integer"} }
    },
    "issue":         {"type": "string"},
    "severity":      {"type": "string", "enum": ["critical", "high", "medium", "low"]},
    "suggested_fix": {"type": "string"},
    "detected_pattern": {"type": "string"},
    "category":      {"type": "string"}
  }
}
```

### Example review output
```json
{
  "findings": [
    {
      "location": {"file": "src/auth.py", "line": 42},
      "issue": "Token compared with == allows timing attack; use hmac.compare_digest.",
      "severity": "high",
      "suggested_fix": "Replace `token == expected` with `hmac.compare_digest(token, expected)`.",
      "detected_pattern": "timing-unsafe-comparison",
      "category": "security"
    }
  ]
}
```

---

## 11. Success Criteria

**MVP success definition:** The fixture repo yields a measurable precision/recall improvement after TR4/TR5, with zero duplicates on re-run and a demonstrable CLAUDE.md-present-vs-absent behavior change.

**Functional requirements (gates):**
- ✅ CI run completes non-interactively via `-p` (no hangs)
- ✅ 100% of findings are valid JSON against the schema and map to real comment locations
- ✅ On the fixture: idiomatic-but-unusual code is **not** flagged; the genuine bug **is**
- ✅ The cross-file bug is caught **only** by the integration pass
- ✅ Severity labels are **identical** for the same issue class across two different PRs
- ✅ A second commit produces **zero** duplicate comments
- ✅ Test-gen suggests **no** already-covered tests
- ✅ Behavior changes with the fixture's CLAUDE.md present vs. absent (TR3)
- ✅ A precision/recall number reported **before vs. after** TR4/TR5 (headline trust metric)
- ✅ A noisy category can be quarantined without losing the good categories (TR9/FR4)

**Quality indicators:** no prose-based assertions (structure/outcomes only); offline-runnable unit suite; versioned prompt.

**UX goals:** findings a wary engineer would act on; readable comment threads across re-pushes.

---

## 12. Implementation Phases

*(Mirrors the spec's PIV build order. Each phase ends with structural validation on the fixture.)*

### Phase 1 — Headless + Structured *(~half day)*
- **Goal:** Prove non-interactive invocation + schema-valid parsing.
- **Deliverables:**
  - ✅ `requirements.txt`, `pytest.ini`, `Makefile` skeleton, `src/` scaffold
  - ✅ `runner.py` — `claude -p --output-format json --json-schema`
  - ✅ `schema.py` + `parse.py` — validate + map to file:line
  - ✅ `make ci-review` prints findings for a minimal fixture PR
- **Validation:** job exits cleanly (no hang); output parses 100% against schema; comments map to real locations.

### Phase 2 — Precision *(~1 day)*
- **Goal:** Cut false positives; stabilize severity.
- **Deliverables:**
  - ✅ Fixture repo with seeded real bug, idiomatic-unusual pattern, cross-file bug
  - ✅ Fixture `CLAUDE.md` carrying review criteria (TR3)
  - ✅ Versioned review command with explicit criteria + few-shot + severity rubric (TR4/TR5)
  - ✅ `severity.py` normalization
  - ✅ `make metrics` — precision/recall on the fixture
- **Validation:** idiomatic pattern **not** flagged; real bug **is**; severity stable across runs; **before/after precision-recall recorded**; CLAUDE.md present-vs-absent behavior change demonstrated.

### Phase 3 — Scale + Dedupe *(~half day)*
- **Goal:** Handle large PRs; kill duplicates.
- **Deliverables:**
  - ✅ `multipass.py` — per-file + integration passes, fresh instances (TR6/TR7)
  - ✅ `dedupe.py` + prior-findings store (TR8/FR3)
  - ✅ `testgen/generate.py` with existing-tests context (FR2)
- **Validation:** no contradictory findings; cross-file bug caught only by integration pass; second commit → zero duplicate comments; no duplicate tests.

### Phase 4 — Trust Loop *(~half day)*
- **Goal:** Make false positives measurable and controllable.
- **Deliverables:**
  - ✅ `detected_pattern` on every finding + `instrument.py` (TR9)
  - ✅ `dismissed_patterns.json` tracking + quarantine config (FR4)
  - ✅ Optional `gh` posting behind `--post`
- **Validation:** dismissed patterns tracked; a high-FP category quarantined without losing good categories.

---

## 13. Future Considerations

- **Real GitHub Actions integration** on a live sample repo (the natural first stretch).
- **Weekly batch tech-debt report** via the Batch API — contrast async batch with the blocking pre-merge check (match API to latency).
- **Dashboard** of dismissed-finding patterns (MVP tracks them in a file).
- **Auto-tuning quarantine:** promote/demote categories based on rolling dismissal rates.
- **Multi-VCS** support beyond GitHub.

---

## 14. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Claude Code CLI output format drifts** (schema flag behavior changes), breaking the parse contract. | Pin behavior via `--json-schema`; validate every output; preserve raw output on parse failure; integration test that fails loudly on drift. |
| 2 | **False positives on idiomatic code** erode trust (the core failure mode). | TR4 explicit criteria + few-shot as the primary lever; fixture's idiomatic-unusual case as a hard gate; before/after precision metric. |
| 3 | **Two CLAUDE.md files conflated** — dev guidance leaks into runtime context or vice versa. | Physical separation (fixture repo owns the runtime CLAUDE.md); TR3 test asserts behavior change present-vs-absent; documented in CLAUDE.md. |
| 4 | **Non-determinism** makes severity/dup tests flaky. | Assert on structure/outcomes not wording; severity via normalized rubric; dedupe by structural key (file, line, pattern) as a backstop to model judgment. |
| 5 | **Multi-pass merge produces contradictory findings.** | Integration pass reconciles cross-file findings; glue dedupes and resolves conflicts; validation gate on "no contradictory findings." |
| 6 | **Accidental live posting** during development. | Emit-by-default; real posting gated behind explicit `--post` flag + integration marker. |

---

## 15. Appendix

### Related documents
- Spec: `docs/04-claude-code-ci-review-bot.md` (FR1–FR4, TR1–TR9, acceptance criteria — non-negotiable)
- Dev guidance: `CLAUDE.md` (this repo)
- Runtime context (to be created): `fixtures/sample-repo/CLAUDE.md`

### Key dependencies
- **Claude Code CLI** — headless: https://code.claude.com/docs/en/headless
- **GitHub Actions** (stretch): https://code.claude.com/docs/en/github-actions
- Claude Code best practices (read 3× per spec)
- Shared venv: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv`

### CCA-F coverage
| Task statement | TRs |
|---|---|
| D3.6 Claude Code in CI/CD | TR1, TR2, TR3, TR8 |
| D4.1 Explicit criteria / FP reduction | TR4, TR5 |
| D4.2 Few-shot prompting | TR4 |
| D4.4 Feedback loops (`detected_pattern`) | TR9 |
| D4.6 Multi-instance & multi-pass | TR6, TR7 |

### Assumptions made
1. **Python 3.10 glue** in the shared monorepo venv *(user-confirmed)*.
2. **Local `make ci-review`** is the MVP CI target; GitHub Actions is a stretch *(user-confirmed)*.
3. **Emit-by-default posting**, real `gh` posting behind a flag *(user-confirmed)*.
4. `jsonschema`/Pydantic for schema validation — final choice deferred to Phase 1.
5. Fixture repo lives under `fixtures/sample-repo/` within this project (not a separate git repo) for MVP simplicity.
