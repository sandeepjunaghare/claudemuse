"""Existing tests for discount — HAPPY PATH ONLY (the coverage context for test-gen).

This file is fed to the test-gen prompt as `{existing_tests}`. It covers the
in-range (happy) path only; the ValueError / boundary cases are intentionally
uncovered so test-gen has a clear net-new case to propose and a clear covered
case to skip. Not collected by the project pytest run (testpaths=tests at repo root).
"""

from discount import apply_discount


def test_apply_discount_basic():
    assert apply_discount(100, 0.1) == 90
