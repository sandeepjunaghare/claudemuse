# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: greenfield (no code yet)

This project is **not started** — the directory holds only the spec (`docs/04-claude-code-ci-review-bot.md`) and `.claude/commands/`, and is **entirely untracked** in the parent `claudemuse` monorepo (`git status` shows the whole dir as untracked; the commits in `git log` belong to sibling projects). Read the spec before writing anything: its functional requirements (**FR1–FR4**), technical requirements (**TR1–TR9**), and acceptance criteria are non-negotiable contracts, not suggestions. It maps to official Exam Scenario 5.

The sibling projects `../customer-support/`, `../multi-agent-research-agent/`, and `../structured-data-extraction-pipe/` are complete references for **monorepo house style** (repo layout, `_tasks/todo.md`, `.agents/plans/`, the `.claude/commands` PIV loop). **But the stack differs sharply:** the siblings are Python apps built on the `anthropic` / `claude-agent-sdk` SDKs. **This project is not an SDK app at all** — it drives **Claude Code itself in headless mode (`claude -p`)** from a CI pipeline, parses its JSON output, and posts GitHub PR comments. Do not reach for `claude-agent-sdk` or the Messages API here; the "agent" is the Claude Code CLI.

## Two CLAUDE.md files — do not conflate them (this is the easy mistake here)

Because TR3 makes CLAUDE.md the bot's *context channel into CI*, this repo will end up with **two distinct CLAUDE.md roles**:

1. **This file** — guidance for a Claude Code instance *developing the bot* (what you're reading).
2. **The reviewed project's CLAUDE.md** — testing standards, fixture conventions, and review criteria that the *bot's headless run* loads to gain project context. This belongs with the **fixture repo** (see below), not here. TR3 is explicitly about demonstrating a behavior change when it's present vs absent.

Keep them separate. When the spec says "supply review criteria via CLAUDE.md," it means #2.

## Environment

- Likely **Python 3.10** for the parse/post glue, via the **shared virtualenv at the monorepo root**: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv` (this project has no venv of its own). Invoke `../../.venv/bin/python` or activate it. Confirm the language choice against the spec's `make ci-review` framing before committing to it — a thin shell + `jq` + `gh` pipeline is also viable.
- Requires the **Claude Code CLI** on PATH (the thing under test) and **`gh`** authenticated for the GitHub API (per global instructions, use `gh` for all GitHub interactions).
- API keys live in the **monorepo-root `.env`** (`ANTHROPIC_API_KEY`) — two levels up from here. Load with `python-dotenv` if Python.
- The stack is **not yet installed for this project** — add a `requirements.txt` (expect `pytest`, `python-dotenv`, and whatever JSON/GitHub glue you pick) and `pip install` into the shared venv when starting the build.
- Mirror the sibling `pytest.ini`: `testpaths = tests` and an `integration` marker for tests that shell out to `claude -p` or hit the GitHub API (so unit tests — schema parsing, dedupe, severity mapping — run offline).

## The core design distinctions (what the exam probes — read first)

The whole point of this build is **developer trust**: a reviewer that emits noise gets muted, and one noisy category poisons trust in all the rest. Everything below exists to earn and keep that trust:

- **Headless, never interactive (TR1).** Invoke `claude -p "..."` so the CI job never blocks on input. A run that can hang on a prompt is an automatic failure.
- **Structured output is the contract (TR2).** Use `--output-format json` with `--json-schema` so findings are machine-parseable, then map each finding (location, issue, severity, suggested fix) to an inline PR comment. Parse against the schema — never scrape prose.
- **Context via CLAUDE.md, not the prompt string (TR3).** Review criteria and conventions reach the run through the reviewed project's CLAUDE.md (see the two-file note above), not hand-pasted into `-p`.
- **Explicit flag/don't-flag criteria + few-shot (TR4).** Replace vague "be conservative" with concrete rules ("flag a comment only when claimed behavior contradicts the code") plus few-shot pairs contrasting *acceptable idiom* vs *genuine bug*. This is the primary false-positive lever.
- **Severity consistency (TR5).** Define critical/high/medium/low each with a concrete code example so the same issue class gets the same label across different PRs.
- **Multi-pass for scale (TR6).** Split large PRs into per-file local passes plus a separate cross-file integration pass — avoids attention dilution and contradictory findings.
- **Independent review instance (TR7).** Review in a *fresh* Claude Code instance without the generator's reasoning context. This beats "self-review" instructions or extended thinking — do not merge generate and review into one context.
- **Duplicate suppression across re-runs (TR8).** On a new commit, feed prior findings into context and instruct Claude to report only new/still-unresolved issues; for test-gen, supply existing tests so it skips covered cases (FR3).
- **False-positive instrumentation (TR9).** Add a `detected_pattern` field to every finding, track dismissed findings by pattern, and be able to **quarantine** a high-false-positive category (disable it) without losing the good categories (FR4, D4.4 feedback loop).

## Intended architecture (from the spec — no code exists yet)

- A **pipeline step** (GitHub Actions workflow, or a `make ci-review` script for local runs) that: checks out the PR diff → invokes `claude -p` with `--json-schema` → parses findings → posts inline comments via `gh`/the GitHub API. A **second step** does test generation.
- The review prompt lives in a **versioned skill/command under `.claude/commands/`** so the whole team shares one prompt — don't inline it in the workflow YAML.
- A **fixture repo** with *seeded* issues is the measurement harness: a real bug (must flag), an idiomatic-but-unusual pattern (must *not* flag), and a cross-file data-flow bug (needs the integration pass). Its CLAUDE.md carries the review criteria for TR3.

## Validation is ground truth, not prose

The fixture repo is ground truth. Assert on structure and outcomes, never on the model's wording. Gate on:

- CI run completes non-interactively via `-p` (no hangs).
- 100% of findings are valid JSON against the schema and map to real comment locations.
- On the fixture: the idiomatic-but-unusual code is **not** flagged; the genuine bug **is**; the cross-file bug is caught only by the integration pass.
- Severity labels are **identical** for the same issue class across two different PRs.
- A second commit produces **zero** duplicate comments; test-gen suggests **no** already-covered tests.
- A **precision/recall number on the fixture set, before vs after TR4/TR5** — the headline trust metric.
- Demonstrated behavior change with the reviewed project's CLAUDE.md present vs absent (TR3).

## Build order (PIV phases)

1. **Headless + structured.** `claude -p` + `--output-format json --json-schema`; parse and print findings. *Validate:* job exits cleanly; output parses; comments map to locations.
2. **Precision.** Explicit criteria + few-shot + severity examples against the fixture repo. *Validate:* idiomatic pattern not flagged; real bug flagged; severity stable across runs.
3. **Scale + dedupe.** Multi-pass for the large PR; prior-findings context on re-runs; existing-tests context for test-gen. *Validate:* no contradictory findings; no duplicate comments on a second commit; no duplicate tests.
4. **Trust loop.** `detected_pattern` instrumentation + category quarantine. *Validate:* false positives are measurable and a noisy category can be disabled without losing the good ones.

## Workflow

Slash commands under `.claude/commands/` drive a PIV loop: `core_piv_loop/prime` (understand the codebase), `core_piv_loop/plan-feature` (deep plan → written to `.agents/plans/{name}.md`), `core_piv_loop/execute` (implement a plan top-to-bottom, running its validation commands), `core_piv_loop/prime-tools`, plus `create-prd`, `first-ask-pre-plan`, and `commit`. Per global instructions, present a plan and get approval before non-trivial work; track it in `_tasks/todo.md`.
