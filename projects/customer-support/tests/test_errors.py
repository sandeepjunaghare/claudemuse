"""Deterministic proof of the TR6 error envelope (no API).

Each builder must set the correct category + retryability + `is_error`, and embed
the model-legible `category=…/retryable=…` tag in the content text (the only
structured surface the model sees — Phase 2 Task-0 finding).
"""

import pytest

from errors import (
    BUSINESS,
    PERMISSION,
    TRANSIENT,
    VALIDATION,
    business_error,
    permission_error,
    transient_error,
    validation_error,
)

# (builder, category, expected_retryable)
_CASES = [
    (transient_error, TRANSIENT, True),
    (validation_error, VALIDATION, False),
    (business_error, BUSINESS, False),
    (permission_error, PERMISSION, False),
]


@pytest.mark.parametrize("builder, category, retryable", _CASES)
def test_envelope_fields(builder, category, retryable):
    """Each builder sets is_error, the category, and the retryability flag."""
    out = builder("Something happened.")
    assert out["is_error"] is True
    assert out["structuredContent"]["errorCategory"] == category
    assert out["structuredContent"]["isRetryable"] is retryable
    assert out["structuredContent"]["isError"] is True
    assert out["structuredContent"]["message"] == "Something happened."


@pytest.mark.parametrize("builder, category, retryable", _CASES)
def test_category_tag_in_text(builder, category, retryable):
    """The model-visible content text carries the terse category/retryable tag."""
    text = builder("Something happened.")["content"][0]["text"]
    assert "Something happened." in text
    assert f"category={category}" in text
    assert f"retryable={'true' if retryable else 'false'}" in text


def test_only_transient_is_retryable():
    """Retryability semantics for this build: transient retries; the rest do not."""
    assert transient_error("x")["structuredContent"]["isRetryable"] is True
    for builder in (validation_error, business_error, permission_error):
        assert builder("x")["structuredContent"]["isRetryable"] is False
