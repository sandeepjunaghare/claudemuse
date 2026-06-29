"""Unit tests for the mock backend (pure, no API key required)."""

from mocks import fixtures


def test_unique_customer_matches_one():
    matches = fixtures.find_customers(name="Alice Wong")
    assert len(matches) == 1
    assert matches[0]["id"] == "C001"


def test_duplicate_name_returns_two():
    # The deliberate John Smith pair forces the ask-for-identifier path (TR7).
    matches = fixtures.find_customers(name="John Smith")
    assert len(matches) == 2
    assert {c["id"] for c in matches} == {"C003", "C004"}


def test_email_disambiguates_duplicate_name():
    matches = fixtures.find_customers(email="jsmith2@example.com")
    assert len(matches) == 1
    assert matches[0]["id"] == "C004"


def test_lookup_is_case_insensitive():
    assert fixtures.find_customers(name="alice wong")[0]["id"] == "C001"
    assert fixtures.find_customers(email="ALICE@EXAMPLE.COM")[0]["id"] == "C001"


def test_unknown_customer_returns_zero():
    assert fixtures.find_customers(name="Nobody Here") == []


def test_no_identifier_returns_zero():
    assert fixtures.find_customers() == []


def test_get_order_returns_record():
    order = fixtures.get_order("O1001")
    assert order is not None
    assert order["status"] == "shipped"
    assert order["customer_id"] == "C001"


def test_get_order_unknown_returns_none():
    assert fixtures.get_order("O9999") is None


def test_heterogeneous_date_formats_preserved():
    # Intentionally NOT normalized in Phase 1 (staged for TR5 in Phase 2).
    assert isinstance(fixtures.get_order("O1001")["placed_at"], int)
    assert fixtures.get_order("O1002")["placed_at"] == "Mar 5, 2025"
    assert fixtures.get_order("O1003")["placed_at"] == "2025-03-15T14:30:00Z"


def test_flaky_seam_is_deterministic():
    """Phase 3 (TR6): the forced-failure seam drives transient 503s deterministically.

    `force_transient_failures(n)` makes the next n `maybe_fail_transient()` calls
    return True, then it returns to the probabilistic path — which the autouse
    `_reset_flaky` fixture pins OFF during the suite, so subsequent calls are False.
    (The production default `FLAKY_503_ENABLED = True` lives in source; tests
    deliberately neutralize the random path for reproducibility.)
    """
    fixtures.force_transient_failures(2)
    assert fixtures.maybe_fail_transient() is True
    assert fixtures.maybe_fail_transient() is True
    assert fixtures.maybe_fail_transient() is False
