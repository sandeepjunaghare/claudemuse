"""Phase 4: stratified accuracy — reported by type AND field, never a lone aggregate (TR8)."""

import audit


def test_compare_field_correctness():
    expected = {"vendor": "Acme", "stated_total": 80.0, "authors": ["A", "B"]}
    actual = {"vendor": "acme", "stated_total": 80.004, "authors": ["B", "A"]}
    result = audit.compare(expected, actual)
    assert result == {"vendor": True, "stated_total": True, "authors": True}


def test_compare_marks_failed_extraction_incorrect():
    assert audit.compare({"vendor": "Acme"}, None) == {"vendor": False}


def test_stratified_report_breaks_down_by_type_and_field():
    items = [
        {"doc_type": "invoice", "expected": {"vendor": "A", "stated_total": 10.0},
         "actual": {"vendor": "A", "stated_total": 999.0}},
        {"doc_type": "invoice", "expected": {"vendor": "B", "stated_total": 20.0},
         "actual": {"vendor": "B", "stated_total": 20.0}},
        {"doc_type": "contract", "expected": {"category": "nda"},
         "actual": {"category": "nda"}},
    ]
    report = audit.stratified_report(items)

    # Per-type, per-field breakdown exists.
    inv = report["by_type"]["invoice"]
    assert inv["fields"]["vendor"]["accuracy"] == 1.0
    assert inv["fields"]["stated_total"]["accuracy"] == 0.5  # one wrong
    assert report["by_type"]["contract"]["fields"]["category"]["accuracy"] == 1.0

    # Overall exists but the segment weakness (stated_total 50%) is visible only in the breakdown.
    assert "overall" in report
    assert report["by_type"]["invoice"]["fields"]["stated_total"]["accuracy"] < report["overall"]["accuracy"]


def test_format_report_is_stratified_text():
    report = audit.stratified_report(
        [{"doc_type": "invoice", "expected": {"vendor": "A"}, "actual": {"vendor": "A"}}]
    )
    text = audit.format_report(report)
    assert "invoice" in text
    assert "vendor" in text
