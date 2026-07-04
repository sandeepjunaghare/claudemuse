# Operations Guide

How to install, configure, and run the multi-agent research system locally.

> **What "running locally" means here.** This is **not** a web service — there is no
> HTTP port and no `localhost:PORT` to open. It is a Python application built on the
> **Claude Agent SDK**. You run it two ways:
>
> 1. **The example script** — `run_example.py` runs one research question end-to-end and
>    prints the cited briefing plus its coverage/provenance/cost metrics.
> 2. **The test suite** — `pytest` runs the deterministic unit suite (free, offline) and,
>    behind a marker, the live acceptance tests (real API calls).
>
> The `web_search` tool server (`src/tools/server.py`) is an MCP **stdio subprocess** that
> the SDK launches and manages automatically. You never start it by hand, and it does not
> listen on a network port.

---

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| **Python** | 3.10 |
| **Shared virtualenv** | This project has **no venv of its own**. It uses the monorepo-root venv: `/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv` (i.e. `../../.venv` from this project). |
| **API credentials** | Either the `claude` CLI logged in **or** an `ANTHROPIC_API_KEY` (see §3). Only needed for live runs — the unit suite runs without any credentials. |
| **`claude` CLI** (recommended) | The Agent SDK drives the `claude` CLI as a subprocess. Live runs authenticate via your existing Claude Code login when the CLI is present. |

All commands below are run **from the project root**:

```bash
cd /Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/multi-agent-research-agent
```

Throughout, `../../.venv/bin/python` is the shared-venv interpreter. (You can `source ../../.venv/bin/activate` instead and drop the prefix; the explicit path is used here so copy-paste always works.)

---

## 2. Install

The stack (`claude-agent-sdk`, `pytest`, `pytest-asyncio`, `python-dotenv`) installs into the **shared** venv — this project adds no venv of its own.

```bash
# From the project root:
../../.venv/bin/python -m pip install -r requirements.txt
```

Verify the install and that all modules import cleanly:

```bash
../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config, errors, provenance, coverage_eval, triage, schemas; from tools.server import format_search; from loop import AgentRun; import coordinator; print('imports ok')"
```

Expected output: `imports ok`.

---

## 3. Configure credentials

API keys live in the **monorepo-root `.env`** — two levels up from this project, at
`/Users/sandeep/Dropbox/dev/experiments/claudemuse/.env`. The app loads it automatically
(`config.load_env()` resolves `parents[3]/.env`). Do **not** create a project-local `.env`.

```dotenv
# /Users/sandeep/Dropbox/dev/experiments/claudemuse/.env
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=...        # present for the monorepo; not used by this project
```

**You have two authentication paths — either one works for live runs:**

- **CLI login (recommended).** If the `claude` CLI is installed and logged in, live runs
  work even with an empty `ANTHROPIC_API_KEY`. Log in interactively by typing this in the
  session prompt (the `!` prefix runs it here so output lands in the conversation):
  ```
  ! claude login
  ```
- **API key.** Set `ANTHROPIC_API_KEY` in the root `.env` above.

Check what the app will detect:

```bash
../../.venv/bin/python -c "import sys; sys.path.insert(0,'src'); import config; config.load_env(); import shutil; print('claude CLI:', bool(shutil.which('claude'))); print('ANTHROPIC_API_KEY present:', config.anthropic_key_present())"
```

If **either** line is `True`, live runs will work. If **both** are `False`, only the unit
suite will run (the live tests skip themselves automatically).

---

## 4. Run the application

### 4a. Run the example (one research question, end-to-end)

```bash
../../.venv/bin/python run_example.py
```

This dispatches the broad question *"What is the impact of AI on creative industries?"*
through the full pipeline and prints:

- `ROUTE` — `fan_out` for a broad question, `single_agent` for a narrow lookup (TR3);
- `DELEGATED TO` / `PEAK CONCURRENT TASKS` — which subagents ran and how many overlapped (TR2);
- `COVERAGE` / `GAPS` / `REFINEMENT ITERATIONS` — facet coverage and self-healing (TR4/TR5);
- `CLAIMS (FR5)` / `all cited` — provenance: claim count and whether every claim carries a source (TR8/FR5);
- `UNAVAILABLE SOURCE ANNOTATED` — that the timed-out source is flagged, not silently dropped (TR7);
- `COST` / `subagent tokens` — token/cost accounting for the ~15× multi-agent run (TR10);
- `REPORT` — the full cited briefing, including a figures table and a `## Coverage & Gaps` section.

> ⚠️ **This is a live run and costs money** — one Opus coordinator plus a Sonnet subagent
> fan-out. Expect roughly a minute or two of wall-clock.

### 4b. Ask your own question (from a Python REPL or script)

```bash
../../.venv/bin/python
```
```python
import asyncio, sys
sys.path.insert(0, "src")
import config; config.load_env()
from coordinator import run_research

run = asyncio.run(run_research("How has AI changed music production?"))
print(run.route, run.coverage, run.gaps)
print("all cited:", run.report.all_claims_have_source())
print(run.final_text)
```

`run_research(question)` is the single entry point. A narrow lookup (e.g. *"What year was
Stable Diffusion released?"*) is routed to the cheap single-agent fallback automatically; a
broad question fans out to parallel subagents and runs the coverage-refinement loop.

---

## 5. Run the tests

### Unit suite — deterministic, offline, free (the gate)

```bash
../../.venv/bin/python -m pytest -m "not integration" -q
```

Expected: **107 passed** in ~1–2s. No credentials or network required — this is the
regression gate to run before every commit.

### Live acceptance suite — real API calls, costs money

```bash
# One phase (cheapest live check):
../../.venv/bin/python -m pytest tests/test_phase4_reliability_live.py -m integration -q

# Full live regression (all phases 1–4):
../../.venv/bin/python -m pytest -m integration -q
```

> ⚠️ The full live suite runs multiple Opus + Sonnet research runs and takes **~20+
> minutes**. It **skips automatically** if no `claude` CLI and no `ANTHROPIC_API_KEY` are
> available (so it never fails for lack of credentials).

### Benchmark (parallel vs. sequential speedup, optional)

```bash
../../.venv/bin/python benchmark_parallel.py
```

Live; prints the wall-clock speedup of parallel fan-out over the sequential baseline (also a paid run).

---

## 6. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `ModuleNotFoundError: claude_agent_sdk` (or `pytest`) | Deps not installed into the shared venv. Re-run §2 with `../../.venv/bin/python -m pip install -r requirements.txt`. |
| `ModuleNotFoundError: config` / `coordinator` when running a script | `src/` isn't on the path. Scripts and tests add it (`sys.path.insert(0, "src")` / `conftest.py`); when running your own snippet, insert `src` on `sys.path` first (see §4b). |
| Live tests all **skipped** | No credentials detected. Run the check in §3 — you need the `claude` CLI logged in **or** `ANTHROPIC_API_KEY` set in the root `.env`. |
| Live run errors with an auth/401 message | `ANTHROPIC_API_KEY` is invalid/expired, or the `claude` CLI isn't logged in. Re-check §3. |
| Looking for a `localhost` URL | There isn't one — this app has no web server (see the note at the top). Use `run_example.py` or the tests. |
| A subagent tool call fails with *"Stream closed"* | The `web_search` tool is served as an **external stdio** MCP process for exactly this reason. Confirm you're on the current code (`main`); the coordinator path must not use the in-process server for subagents. |
| Want fewer paid runs | Default to the unit suite (`-m "not integration"`). Run a single live test file rather than the full `-m integration` sweep. |

---

## 7. Quick reference

```bash
# From the project root:
cd /Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/multi-agent-research-agent

../../.venv/bin/python -m pip install -r requirements.txt   # install (once)
../../.venv/bin/python run_example.py                        # run one research briefing (live)
../../.venv/bin/python -m pytest -m "not integration" -q     # unit suite (offline, free)
../../.venv/bin/python -m pytest -m integration -q           # live acceptance suite (paid)
```

**Key facts:** Python 3.10 · shared venv at `../../.venv` (no project venv) · credentials in
the monorepo-root `.env` · entry point `coordinator.run_research(question)` · no network
port. See `CLAUDE.md` for architecture and `docs/02-multi-agent-research-system.md` for the
requirements spec.
