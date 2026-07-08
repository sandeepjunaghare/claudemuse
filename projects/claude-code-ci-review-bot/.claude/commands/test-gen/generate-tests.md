---
description: Generate net-new tests for a change, skipping covered cases
---

You generate **net-new** pytest tests for a single code change supplied as a
unified diff. You are given the project's **existing tests** for this code.
Propose tests ONLY for behaviors the existing tests do NOT already cover —
re-proposing a case that is already covered is noise and gets the tool muted, so
**skipping covered cases is the priority**.

Also honor the project's testing standards in its `CLAUDE.md` (loaded
automatically from the working directory): the framework, naming convention, and
one-behavior-per-test discipline it states are authoritative. Follow them when
you compose each test.

Emit every proposed test **only** through the structured output — never write
tests as prose in your reply. If every meaningful behavior of the changed code is
already covered by the existing tests, return an empty `tests` array.

## PROPOSE a test only when it exercises a behavior NOT already covered

- An untested **error / exception path** (e.g. a guard that raises).
- An **uncovered branch** of the changed code.
- An **unhandled edge or boundary** input.
- A **distinct valid-input class** the existing tests don't reach.

## DON'T propose

- A test whose behavior an existing test already covers — **even if you would
  name it differently**. (Read the existing tests carefully first.)
- A test that merely restates the happy path an existing test already asserts.
- Trivial or tautological tests; tests for unchanged code.

## Few-shot: covered vs. uncovered (learn the discrimination, don't memorize)

1. **No test** — the existing `test_apply_discount_basic` already asserts a valid
   in-range rate (`apply_discount(100, 0.1) == 90`). The happy path is covered →
   do NOT propose another happy-path test.
2. **Test** — no existing test exercises an out-of-range `rate`. The function
   raises `ValueError` when `rate < 0 or rate > 1`, and that branch is untested →
   propose `case: rate-out-of-range` with a test asserting
   `pytest.raises(ValueError)` on e.g. `apply_discount(100, 2)`.

## Field guidance (aligned to the output schema)

- `target.file`: the path after `+++ b/` in the diff.
- `target.symbol`: the changed function/method the test covers.
- `test_name`: a valid pytest function name, `test_<symbol>_<behavior>` (e.g.
  `test_apply_discount_rejects_out_of_range_rate`).
- `case`: a short kebab-case slug naming the behavior under test (e.g.
  `rate-out-of-range`) — this is the dedupe identity, so make it specific.
- `description`: one sentence naming the behavior the test exercises.
- `test_code`: a complete, runnable pytest test function — imports plus the
  `def test_…` body.

The change under review:

```diff
{diff}
```

The project's existing tests for this code (propose only what these do NOT cover):

```python
{existing_tests}
```
