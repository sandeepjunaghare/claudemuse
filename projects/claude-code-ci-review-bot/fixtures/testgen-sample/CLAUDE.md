# Project conventions — testgen-sample

> This is the **reviewed project's** CLAUDE.md — the test-gen bot's *runtime
> context channel* (TR3). It carries the **testing standards** that the headless
> `claude -p` test-generation pass auto-loads from the working directory. It is
> NOT bot-dev guidance, and it is NOT the review sample-repo's CLAUDE.md. Do not
> conflate the three.

## Testing standards (authoritative — follow these when proposing tests)

- **Framework:** `pytest`. Tests are plain functions named `test_<...>`; use
  `pytest.raises(...)` to assert on exception paths.
- **One behavior per test.** Each test exercises a single behavior of the code
  under test; do not bundle unrelated assertions.
- **Naming:** name tests `test_<function>_<behavior>` (e.g.
  `test_apply_discount_rejects_out_of_range_rate`) so the intent is legible.
- **Cover the risky paths.** Prioritize error/exception branches and edge or
  boundary inputs that the existing tests do not already cover.
- **Never duplicate an existing test's case.** If a behavior is already covered
  by an existing test, do not propose another test for it — a redundant
  suggestion is noise and erodes trust in the tool.
