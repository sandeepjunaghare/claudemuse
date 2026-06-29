---
name: pr-review
description: Review a pull request — read the diff, check for correctness bugs, surface reuse/simplification opportunities, and flag missing tests or docs. Use when the user asks to review a PR, look at a diff, or evaluate proposed changes before merging.
---

# PR Review

## When to use

Trigger when the user says any of:

- "Review this PR" / "review PR #123"
- "Look at the diff"
- "Anything wrong with my changes?"
- "Ready to merge?"

## Steps

1. **Load the diff**
   - If a PR number is given: `gh pr view <num> --json title,body,files` and `gh pr diff <num>`.
   - Otherwise: `git diff <base>...HEAD` against the merge base.
2. **Read the PR description** — what is the author trying to do? Reviews drift when you skip this.
3. **Walk the diff file-by-file**. For each hunk, ask:
   - Does this actually do what the description claims?
   - Any correctness bugs (off-by-one, null deref, race, missing await)?
   - Existing helper/util that already does this?
   - Is the test coverage proportional to the risk?
4. **Check for what's missing** — tests, migrations, feature flags, error handling at boundaries.
5. **Report findings** as a short list. Each finding: `file:line — issue — suggested fix`. Sort by severity (correctness > reuse > style).

## References

- `references/checklist.md` — review checklist by change type (refactor / feature / bugfix / migration).

## Don'ts

- Don't restate what the diff does — the author already knows.
- Don't nitpick style if a linter would catch it.
- Don't suggest sweeping refactors in a small PR; note them separately as follow-ups.
