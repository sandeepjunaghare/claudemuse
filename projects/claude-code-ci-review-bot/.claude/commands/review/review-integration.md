---
description: Cross-file integration review of a whole diff — data-flow / contract defects only
---

You are reviewing an **entire pull-request diff spanning multiple files**,
specifically for defects that only appear when reasoning **across files**.
Single-file issues are handled by a separate per-file review — **do NOT report
them here**. Your findings become inline PR comments, so **precision is the
priority**: when in doubt, do **not** flag.

Also honor any project conventions in the project's `CLAUDE.md` (loaded
automatically from the working directory). A pattern that is correct *under the
project's stated conventions* is **not** a finding.

Emit every finding **only** through the structured output — never write prose
findings in your reply. If there are no genuine cross-file issues, return an
empty `findings` array.

## FLAG only CROSS-FILE issues — one of these must be concretely true

- A **producer** writes a dict key / field / argument name in one file that a
  **consumer** in another file reads under a *different* name → runtime
  `KeyError` / `AttributeError` / missing value. (e.g. one file writes
  `"user_id"`, another reads `rec["userId"]`.)
- A function's **signature or return shape changed** in one file, but a **caller
  in another file** was not updated to match.
- An **enum / constant / contract** defined in one file is used **inconsistently**
  by another file (a value that can never match, a shape the other side doesn't
  expect).

## DON'T flag

- Anything visible within a **single file in isolation** (that's the per-file
  review's job) — including a same-file None-deref, off-by-one, or unhandled
  error path.
- Style, formatting, naming.
- Hypotheticals with **no concrete cross-file trigger** ("a caller might…").
- Anything the project's `CLAUDE.md` declares intentional or conventional.

## Few-shot: cross-file mismatch vs. consistent contract

1. **Finding** — `ingest.to_record` writes `{"user_id": user.id, ...}` while
   `summary.user_ids` reads `rec["userId"]`. The producer and consumer disagree
   on the key spelling → `KeyError` at runtime on every record.
   Flag: `detected_pattern: cross-file-key-mismatch`, `severity: critical`,
   `category: correctness`, located at either the producer write or the consumer
   read.
   **No finding** — a producer writes `"user_id"` and **every** consumer reads
   `"user_id"`. The contract is consistent across files. Emit nothing.

## Severity rubric (each level with a concrete example) — TR5

- **critical** — a cross-module contract break that crashes a production path.
  *Example:* a producer writing key `"user_id"` while the consumer reads
  `"userId"` → runtime `KeyError`; a caller passing args a changed signature
  rejects.
- **high** — a cross-file mismatch that yields a wrong result on a realistic
  input without an outright crash.
- **medium** — a cross-file inconsistency that misbehaves only in an edge case.
- **low** — a fragile cross-file coupling with no current failure.

## Field guidance

- `location.file`: the path after `+++ b/` for the file you're pointing at.
- `location.line`: the line in the **new** file (count forward from the
  `@@ -old,+new @@` header through `+` and context lines).
- `issue`: the concrete cross-file problem, one sentence naming both ends.
- `severity`: `critical` | `high` | `medium` | `low`, per the rubric above.
- `suggested_fix`: the specific change that reconciles the two files.
- `detected_pattern`: a short kebab-case slug from the controlled set when it
  applies — `cross-file-key-mismatch`, `key-error` — else a concise new slug.
- `category`: one of `correctness`, `security`, `performance`, `maintainability`.

Unified diff to review (all files):

```diff
{diff}
```
