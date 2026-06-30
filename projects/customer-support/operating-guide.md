# Operating Guide — Customer Support Resolution Agent

How to install, configure, and run this project. It is a **Claude Agent SDK**
application with mocked backends behind four MCP tools. There is no standalone
binary — you drive it through its small Python API (`loop.run_turn` for a single
turn, `session.run_conversation` for a multi-turn conversation) and validate it
with the test suite. This guide covers both.

> Paths below assume the repo layout `…/claudemuse/projects/customer-support/`.
> The shared virtualenv and the `.env` live at the **workspace root**
> (`…/claudemuse/`), two levels above this project — not inside it.

---

## 1. Prerequisites

- **Python 3.10** (the shared venv is built on 3.10).
- The **`claude` CLI** *or* an **`ANTHROPIC_API_KEY`**. The Agent SDK drives the
  `claude` CLI as a subprocess, which authenticates via your existing Claude Code
  login **or** the env var. Either one is enough to make live runs work; if
  neither is present, the live (integration) tests auto-skip and only the
  deterministic suite runs.
- `git` (to clone) and network access to the Anthropic API for live runs.

Check Python and the CLI:

```bash
python3 --version          # expect 3.10.x
claude --version           # optional but recommended for live runs
```

---

## 2. Install

This project uses the **shared workspace virtualenv** at
`…/claudemuse/.venv` — it does **not** have its own. For convenience, define:

```bash
# Run from anywhere; adjust the absolute prefix if your checkout differs.
export VENV=/Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv
export PY="$VENV/bin/python"
export PROJ=/Users/sandeep/Dropbox/dev/experiments/claudemuse/projects/customer-support
```

### If the venv already exists
Just install/refresh the dependencies:

```bash
cd "$PROJ"
"$PY" -m pip install -r requirements.txt
```

### If you need to create the venv from scratch

```bash
python3 -m venv /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$PROJ/requirements.txt"
```

Dependencies (`requirements.txt`): `claude-agent-sdk`, `pytest`,
`pytest-asyncio`, `python-dotenv`. This guide was validated against
**claude-agent-sdk 0.2.110**.

Verify the install:

```bash
"$PY" -c "import claude_agent_sdk; print('sdk', claude_agent_sdk.__version__)"
```

---

## 3. Configure credentials

API keys are loaded from the **workspace-root** `.env`
(`…/claudemuse/.env`) — one level above `projects/`. `src/config.py` resolves
this path from `__file__`, so the working directory doesn't matter.

Create or edit `…/claudemuse/.env`:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
# VOYAGE_API_KEY=...        # not required by this project
```

If you authenticate the `claude` CLI instead (`claude` login), the
`ANTHROPIC_API_KEY` can be left empty — live runs still work via CLI auth.

Confirm credentials resolve:

```bash
cd "$PROJ"
"$PY" -c "import sys; sys.path.insert(0,'src'); import config; config.load_env(); print('API key present:', config.anthropic_key_present())"
```

The model used is set in `src/config.py` (`MODEL = "claude-opus-4-8"`).

---

## 4. Run the agent

The agent has no CLI; you invoke it from Python. Both drivers build options with
`agent.build_options()` (least-privilege tools + the deterministic hooks).

> **Run scripts from files, don't paste them.** Multi-line snippets (especially
> shell heredocs) get scrambled when pasted into an interactive terminal —
> bracketed paste reorders lines and collides inline comments. Two ready-to-run
> example files ship at the project root; use them, or save your own `.py` file
> and run it with `"$PY" yourfile.py`.

### 4a. One-shot (single turn) — `run_example.py`

```bash
cd "$PROJ"
"$PY" run_example.py
```

Expected output:

```
TOOLS:  ['get_customer', 'lookup_order']
OUTCOME: success
REPLY:  Hi Alice! I've verified your identity. Here's the status of your order:
        - Order O1001: Shipped  - Total: $42.00  - Placed: March 1, 2025 ...
```

The script (abridged) — edit the prompt to try other messages:

```python
import asyncio, sys
sys.path.insert(0, "src")
import config; config.load_env()
from agent import build_options
from loop import run_turn

async def main():
    run = await run_turn(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of order O1001?",
        build_options(),
    )
    print("TOOLS: ", run.tool_calls)   # e.g. ['get_customer', 'lookup_order']
    print("OUTCOME:", run.subtype)     # 'success' on a clean resolution
    print("REPLY: ", run.final_text)

asyncio.run(main())
```

### 4b. Multi-turn conversation (persistent session) — `run_conversation_example.py`

`session.run_conversation` opens one `ClaudeSDKClient` session so case facts,
verified identity, and history carry across turns (TR9 / FR6) — turn 2 recalls the
exact order id and amount from turn 1 with **no tool calls**, via the injected
case-facts block.

```bash
cd "$PROJ"
"$PY" run_conversation_example.py
```

Expected output (note `TOOLS: []` on turn 2 — the figures come from the injected
case-facts block, not a re-lookup):

```
--- turn 1 ---
TOOLS: ['get_customer', 'lookup_order']
REPLY: ... Order O1001 — Status: Shipped — Total: $42.00 ...
--- turn 2 ---
TOOLS: []
REPLY: ... Order number: O1001 — Exact amount: $42.00 ...
```

The script (abridged) — edit the prompt list to script your own conversation:

```python
import asyncio, sys
sys.path.insert(0, "src")
import config; config.load_env()
from agent import build_options
from session import run_conversation

async def main():
    convo = await run_conversation([
        "Hi, I'm Alice Wong, alice@example.com — what's the status of order O1001?",
        "Thanks — remind me the exact amount and order number.",
    ], build_options())
    for i, turn in enumerate(convo.turns, 1):
        print(f"--- turn {i} ---")
        print("TOOLS:", turn.tool_calls)
        print("REPLY:", turn.final_text)

asyncio.run(main())
```

### 4c. Interactive REPL (optional convenience)

Save this as `repl.py` in the project root, then run `"$PY" repl.py`. It keeps a
single conversation alive so you can chat turn-by-turn; type `quit` to exit.

```python
import asyncio, sys
sys.path.insert(0, "src")
import config; config.load_env()
from agent import build_options
from session import run_conversation

async def main():
    options = build_options()
    history = []
    print("Customer-support agent. Type 'quit' to exit.")
    while True:
        msg = input("you> ").strip()
        if msg.lower() in {"quit", "exit"}:
            break
        history.append(msg)
        convo = await run_conversation(history, options)   # replays full history
        print("agent>", convo.turns[-1].final_text)

asyncio.run(main())
```

> Note: this simple REPL replays the full prompt history each turn (the drivers
> are designed around scripted prompt lists). It's fine for manual exploration;
> for production you'd hold the `ClaudeSDKClient` open across turns.

---

## 5. Run the tests

Tests live in `tests/` and split into two groups via the `integration` marker
(`pytest.ini`): **deterministic** (no API, the bulk of the proof) and **live**
(real Agent SDK calls, auto-skipped without credentials).

```bash
cd "$PROJ"

# Deterministic suite only — fast, zero API calls, zero cost:
"$PY" -m pytest -m "not integration"

# Live suite only (needs the claude CLI or ANTHROPIC_API_KEY):
"$PY" -m pytest -m integration

# Everything:
"$PY" -m pytest
```

Useful invocations:

```bash
# The headline 20-case resolution-rate gate (>=80% target); -s prints the table:
"$PY" -m pytest tests/test_phase4_scenarios_live.py -v -s

# A single deterministic file:
"$PY" -m pytest tests/test_tools_trim.py -v
```

Expected baseline: the deterministic suite is **all green** with zero API calls;
the live 20-case suite measures **first-contact resolution** and should sit
comfortably at or above the 80% target (guardrail cases — over-limit refund and
duplicate-name — must pass at 100%).

---

## 6. Project layout (orientation)

```
src/
  agent.py            build_options() + the behavior-only SYSTEM_PROMPT; wires all hooks
  loop.py             run_turn() — one-shot driver; _ingest_message() shared helper
  session.py          run_conversation() — multi-turn ClaudeSDKClient driver
  config.py           MODEL, refund limit, workspace .env loading
  tools/server.py     the four MCP tools (get_customer, lookup_order, process_refund, escalate_to_human)
  hooks/              deterministic guardrails: prerequisite_gate, refund_gate, normalize,
                      handoff_gate, case_facts_recorder (+ case_facts_inject), verified_store
  context/case_facts.py   session-keyed case-facts store (TR9a)
  mocks/fixtures.py   seeded customers/orders, duplicate-name pair, flaky-503 seam, verbose record
tests/                deterministic + live suites; scenarios.py = the 20-case table
docs/                 the spec (01-…) and PRD (02-…) — source of truth for intent
run_example.py              one-shot example (section 4a)
run_conversation_example.py multi-turn example (section 4b)
```

---

## 7. Troubleshooting

- **Live tests are skipped / "No `claude` CLI or ANTHROPIC_API_KEY".** Install
  and log in to the `claude` CLI, or set `ANTHROPIC_API_KEY` in the workspace
  `.env`. The deterministic suite runs regardless.
- **`ModuleNotFoundError: claude_agent_sdk`.** You're not using the shared venv —
  invoke `"$PY"` (the venv's interpreter), not the system `python`, and re-run
  `pip install -r requirements.txt`.
- **`API key present: False` but live runs still work.** Expected when you're
  authenticated through the `claude` CLI rather than the env var.
- **Import errors when running scripts by hand.** The source modules use absolute
  imports with `src/` on `sys.path`; every snippet above does
  `sys.path.insert(0, "src")` and runs from the project root. Keep both.
- **A live scenario occasionally fails.** Live behavior is model-driven; the gate
  is the *rate* (≥80%) plus 100% on guardrails. Re-run, and if a non-guardrail
  case is persistently flaky, tune its prompt/few-shot — never weaken a guardrail
  predicate (see the EXECUTION NOTES in `.agents/plans/customer-support-phase-4.md`).
```
