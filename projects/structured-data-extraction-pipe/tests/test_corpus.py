"""The labeled set is ground truth: it loads, is segmented by type, and seeds every edge case."""

from data.corpus import LABELED, SAMPLES, by_tag
from schemas import SCHEMA_REGISTRY


def test_labeled_set_size_and_types():
    assert len(LABELED) >= 10  # 10–20 known-answer docs
    for doc in LABELED:
        assert doc.doc_type in SCHEMA_REGISTRY
        assert isinstance(doc.expected, dict)


def test_segmented_by_type():
    types = {doc.doc_type for doc in LABELED}
    assert {"invoice", "contract", "paper"} <= types


def test_every_edge_case_is_seeded():
    for tag in ("conflict", "absent_field", "novel_category", "missing_info", "format_error"):
        assert by_tag(tag), f"no labeled doc tagged {tag!r}"


def test_samples_expose_the_edge_cases():
    assert set(SAMPLES) >= {
        "bad_sum_invoice",
        "absent_field_invoice",
        "novel_category_contract",
        "format_error_invoice",
        "missing_info_paper",
    }


def test_ids_are_unique():
    ids = [doc.id for doc in LABELED]
    assert len(ids) == len(set(ids))
