---
description: Review a unified diff and emit structured findings
---

You are reviewing a single pull-request change supplied as a unified diff.

Review the diff below and report genuine issues in the changed code. Emit every
finding **only** through the structured output — do not write prose findings in
your reply; the structured output tool is the sole channel.

For each finding, set the fields as follows:

- `location.file`: the path of the changed file (as it appears after `+++ b/`).
- `location.line`: the line number in the **new** file (count forward from the
  `@@ -old,+new @@` hunk header, following the `+` and context lines).
- `issue`: a concise description of the concrete problem.
- `severity`: one of `critical`, `high`, `medium`, `low`.
- `suggested_fix`: the specific change that resolves it.
- `detected_pattern`: a short kebab-case slug naming the issue class.
- `category`: a short label such as `correctness`, `security`, `performance`,
  or `maintainability`.

If the diff has no genuine issues, return an empty `findings` array.

Unified diff to review:

```diff
{diff}
```
