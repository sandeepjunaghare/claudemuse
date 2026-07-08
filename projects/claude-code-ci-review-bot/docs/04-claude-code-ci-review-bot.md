# Project 04 — Claude Code CI/CD Review & Test Bot

> **Pitch:** Wire Claude Code into a real CI pipeline that reviews pull requests and generates tests —
> headless, machine-parseable, low-false-positive, and trusted by developers.
> **Primary domains:** D3 Claude Code Config & Workflows · D4 Prompt Engineering & Structured Output.
> **Difficulty:** ●●○ · **Effort:** 2–3 days · maps to **official Exam Scenario 5**.

## Problem statement

An engineering team wants automated PR review and test generation that developers actually trust. You integrate
**Claude Code in headless mode** into CI (GitHub Actions or a local pipeline runner). It must emit
**structured, parseable** findings for inline comments, **minimize false positives**, avoid **duplicate
comments** across commits, and produce **consistent severity** — or developers will mute it.

## Background / why it matters

CI is where Claude Code meets automation: non-interactive execution, structured output for tooling, and prompt
engineering for precision. The exam emphasizes that trust collapses if one noisy category poisons the rest, and
that an independent review instance beats self-review.

## Goals & non-goals

- **Goals:** headless invocation; JSON-schema output for inline comments; explicit review criteria + few-shot to
  cut false positives; multi-pass review for large PRs; duplicate-comment suppression; consistent severity;
  CLAUDE.md as the context channel into CI.
- **Non-goals:** building a hosted bot service, supporting every VCS, or replacing human review entirely.

## Functional requirements

- FR1. On a PR, run a review and post inline comments with location, issue, severity, and suggested fix.
- FR2. Generate tests for changed code that don't duplicate existing coverage.
- FR3. On re-runs after new commits, post only **new or still-unresolved** issues.
- FR4. Keep false positives low enough that developers act on findings.

## Technical requirements (mapped to CCA-F task statements)

- **TR1 — Headless invocation (D3.6).** Run `claude -p "..."` (non-interactive) so the job never hangs on input.
- **TR2 — Structured output (D3.6).** Use `--output-format json` with `--json-schema` so findings are
  machine-parseable and post as inline comments. Parse and map to PR comment locations.
- **TR3 — Context via CLAUDE.md (D3.6).** Supply testing standards, fixture conventions, and review criteria in
  CLAUDE.md so the CI-invoked run has project context (don't hand-paste into the prompt string).
- **TR4 — Explicit criteria + few-shot (D4.1 / D4.2).** Replace vague "be conservative" with explicit
  flag/don't-flag criteria (e.g., "flag a comment only when claimed behavior contradicts the code"), plus
  few-shot examples contrasting acceptable patterns vs genuine issues so the model generalizes.
- **TR5 — Severity consistency (D4.1).** Define each severity level (critical/high/medium/low) with a concrete
  code example so classification is consistent across PRs.
- **TR6 — Multi-pass review (D4.6).** For large PRs, split into per-file local-analysis passes plus a separate
  cross-file integration pass to avoid attention dilution and contradictory findings.
- **TR7 — Independent review instance (D4.6).** Review in a fresh instance without the generator's reasoning
  context — more effective than "self-review" instructions or extended thinking.
- **TR8 — Duplicate suppression (D3.6).** On re-runs, include prior review findings in context and instruct
  Claude to report only new/unaddressed issues. For test-gen, provide existing tests so it skips covered cases.
- **TR9 — False-positive instrumentation (D4.4).** Add a `detected_pattern` field to findings; track dismissed
  findings by pattern; temporarily disable any high-false-positive category while you refine its prompt.

## Architecture guidance (references, not code)

- A pipeline step (GitHub Actions workflow or a `make ci-review` script) that: checks out the PR diff, invokes
  `claude -p` with `--json-schema`, parses findings, and posts comments via the GitHub API. A second step for
  test generation. CLAUDE.md (+ `.claude/rules/` for test conventions) carries standards. Keep the review prompt
  in a versioned skill/command so the whole team shares it.
- Build a small fixture repo with seeded issues (a real bug, an idiomatic-but-unusual pattern that should *not*
  be flagged, a cross-file data-flow bug) to measure precision/recall.

## Build phases (PIV)

1. **Headless + structured.** `claude -p` + `--output-format json --json-schema`; parse and print findings.
   *Validate:* job exits cleanly; output parses; comments map to locations.
2. **Precision.** Explicit criteria + few-shot + severity examples on the fixture repo. *Validate:* the
   idiomatic pattern is not flagged; the real bug is; severity is stable across runs.
3. **Scale + dedupe.** Multi-pass for the large PR; prior-findings context for re-runs; existing-tests context
   for test-gen. *Validate:* no contradictory findings; no duplicate comments on a second commit; no duplicate tests.
4. **Trust loop.** `detected_pattern` instrumentation + category quarantine. *Validate:* false positives are
   measurable and a noisy category can be disabled without losing the good ones.

## Acceptance criteria

- [ ] CI run completes non-interactively via `-p` (no hangs).
- [ ] Findings are valid JSON against the schema and post as inline comments.
- [ ] On a seeded fixture, the idiomatic-but-unusual code is **not** flagged; the genuine bug **is**.
- [ ] Severity labels are identical for the same issue class across two different PRs.
- [ ] A second commit produces **no** duplicate comments; test-gen suggests **no** already-covered tests.
- [ ] Project standards reach the run via CLAUDE.md (demonstrate behavior change when present vs absent).
- [ ] A precision/recall number on the fixture set, before vs after TR4/TR5.

## Validation strategy

Treat the fixture repo as ground truth: known bugs (should flag), known idioms (should not), known cross-file
issue (needs integration pass). Measure precision/recall and duplicate rate as your gate.

## Stretch goals

- Real GitHub Actions integration on a sample repo. · A weekly batch "tech-debt report" via the Batch API
  (contrast with the blocking pre-merge check — match API to latency). · A dashboard of dismissed-finding patterns.

## CCA-F coverage

| Task statement | Exercised by |
|---|---|
| D3.6 Claude Code in CI/CD (-p, json, CLAUDE.md context, dedupe) | TR1, TR2, TR3, TR8 |
| D4.1 Explicit criteria / false-positive reduction | TR4, TR5 |
| D4.2 Few-shot prompting | TR4 |
| D4.4 Feedback loops (detected_pattern) | TR9 |
| D4.6 Multi-instance & multi-pass review | TR6, TR7 |

**Read first:** [Headless mode](https://code.claude.com/docs/en/headless);
[GitHub Actions](https://code.claude.com/docs/en/github-actions); Claude Code best practices (read 3×).
