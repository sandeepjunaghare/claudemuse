"""Deterministic unit table for `errors` (TR7). No SDK, no API, no network.

Ground truth for the access-failure-vs-valid-empty distinction: `is_retryable` is total
(unknown strings never raise, never count as retryable), and `ErrorEnvelope.render` emits
the machine-readable `ERROR:` block carrying the four things TR7 requires.
"""

import pytest

import errors


# --- is_retryable -------------------------------------------------------------

@pytest.mark.parametrize(
    "failure_type,expected",
    [
        (errors.FAILURE_ACCESS_TIMEOUT, True),
        (errors.FAILURE_ACCESS, True),
        (errors.FAILURE_VALID_EMPTY, False),
        ("some-unknown-type", False),  # unknown → not retryable, never raises
        ("", False),
    ],
)
def test_is_retryable_truth_table(failure_type, expected):
    assert errors.is_retryable(failure_type) is expected


# --- ErrorEnvelope.render -----------------------------------------------------

def test_render_contains_required_keys():
    env = errors.ErrorEnvelope(
        type=errors.FAILURE_ACCESS_TIMEOUT,
        attempted_query="AI music",
        is_retryable=True,
        failed_source="Recording Artists Coalition",
        alternative="report this source as unavailable; other sources remain valid.",
    )
    text = env.render()
    assert "ERROR:" in text
    assert errors.FAILURE_ACCESS_TIMEOUT in text
    assert "retryable: true" in text
    assert "attempted_query:" in text and "AI music" in text
    assert "Recording Artists Coalition" in text


def test_render_without_failed_source_does_not_raise():
    env = errors.ErrorEnvelope(
        type=errors.FAILURE_VALID_EMPTY,
        attempted_query="zzz",
        is_retryable=False,
    )
    text = env.render()  # must not raise
    assert "ERROR:" in text
    assert "retryable: false" in text
    assert "failed_source" not in text  # skipped when unset
