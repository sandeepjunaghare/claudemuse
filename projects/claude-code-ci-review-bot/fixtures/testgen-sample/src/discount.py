"""Discount pricing helper.

SEEDED TEST-GEN FIXTURE INTENT: a CORRECT function with a guarded error branch.
The existing test (tests/test_discount.py) covers ONLY the happy path
(a valid in-range rate). The uncovered behavior is the ValueError branch
(rate < 0 or rate > 1) and the boundaries (rate == 0, rate == 1). Test-gen must
propose a net-new test for the uncovered error path and must NOT re-propose the
already-covered happy path. There is deliberately NO bug here — test-gen's job
is coverage, not bug-finding.
"""


def apply_discount(price, rate):
    """Return ``price`` reduced by ``rate`` (a fraction in [0.0, 1.0])."""
    if rate < 0 or rate > 1:
        raise ValueError("rate must be a fraction in [0.0, 1.0]")
    return price * (1 - rate)
