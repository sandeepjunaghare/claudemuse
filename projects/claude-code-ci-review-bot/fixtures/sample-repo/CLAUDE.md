# Project conventions — sample-repo

> This is the **reviewed project's** CLAUDE.md — the bot's *runtime context
> channel* (TR3). It carries the conventions and review policy that the headless
> `claude -p` review auto-loads from the working directory. It is NOT bot-dev
> guidance. Do not conflate it with the bot repo's own CLAUDE.md.

## Domain conventions (authoritative — respect these when reviewing)

- **Settings/config reads must be total — they must never raise.** By deliberate
  resilience policy, `settings.get()` (and any config accessor) catches **all**
  exceptions and returns the documented default from `DEFAULTS` on any failure. A
  broad `except Exception:` that falls back to a default in settings access is
  **intentional and correct** here — it guarantees the app boots even when a
  config source is unavailable or malformed. **Do not flag broad exception
  handling in settings/config reads as an error-swallowing bug; it is policy.**

## Review policy

- Flag only **genuine defects**: code that produces a wrong result, crashes on a
  realistic input, or is unsafe. Respect the documented conventions above — a
  pattern that is correct *under our conventions* is not a finding.
- Do **not** flag style, naming, formatting, or idiomatic-but-unusual code that
  is correct under these conventions.

## Severity policy

Use the four-level scale and keep the same issue class at the same level across
PRs:

- **critical** — data corruption, RCE, auth bypass, or a cross-module contract
  break that crashes production paths.
- **high** — crash on a realistic input (e.g. dereferencing a value that a
  lookup can return as `None`).
- **medium** — wrong result in an edge case.
- **low** — minor correctness risk with no crash.
