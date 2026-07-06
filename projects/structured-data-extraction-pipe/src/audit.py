"""Stratified accuracy audit (TR8).

An aggregate 97% can hide 40% errors for one document type or one field — so accuracy is
always reported **by document type and by field**, never as a lone aggregate. Correctness
is checked against the labeled set's known answers, structurally (numeric tolerance,
case-insensitive strings, order-insensitive lists), never against the model's wording.
"""

from typing import Dict, List, Optional

_FLOAT_TOLERANCE = 0.01


def _values_match(expected, actual) -> bool:
    """Structural equality: floats within tolerance, strings normalized, lists order-insensitive."""
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= _FLOAT_TOLERANCE
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    if isinstance(expected, list) and isinstance(actual, list):
        norm = lambda xs: sorted(x.strip().lower() if isinstance(x, str) else x for x in xs)
        try:
            return norm(expected) == norm(actual)
        except TypeError:
            return expected == actual
    return expected == actual


def compare(expected: Dict, actual: Optional[Dict]) -> Dict[str, bool]:
    """Per-field correctness of one extraction against its known answer.

    Only the fields present in `expected` (the ground-truth subset) are scored. A failed
    extraction (`actual is None`) scores every expected field incorrect.
    """
    result: Dict[str, bool] = {}
    for field, exp_value in expected.items():
        if actual is None:
            result[field] = False
        else:
            result[field] = _values_match(exp_value, actual.get(field))
    return result


def stratified_report(items: List[Dict]) -> Dict:
    """Aggregate per-field correctness into a per-type + per-field report.

    `items` = list of `{"doc_type", "expected", "actual"}`. Returns a nested report with a
    per-type/per-field breakdown and an overall figure (kept only alongside the breakdown,
    never as a standalone number).
    """
    by_type: Dict[str, Dict] = {}
    overall_correct = overall_total = 0

    for item in items:
        dtype = item["doc_type"]
        correctness = compare(item["expected"], item.get("actual"))
        bucket = by_type.setdefault(dtype, {"fields": {}, "correct": 0, "total": 0})
        for field, ok in correctness.items():
            fstat = bucket["fields"].setdefault(field, {"correct": 0, "total": 0})
            fstat["total"] += 1
            fstat["correct"] += int(ok)
            bucket["total"] += 1
            bucket["correct"] += int(ok)
            overall_total += 1
            overall_correct += int(ok)

    for bucket in by_type.values():
        for fstat in bucket["fields"].values():
            fstat["accuracy"] = fstat["correct"] / fstat["total"] if fstat["total"] else 0.0
        bucket["accuracy"] = bucket["correct"] / bucket["total"] if bucket["total"] else 0.0

    return {
        "by_type": by_type,
        "overall": {
            "correct": overall_correct,
            "total": overall_total,
            "accuracy": overall_correct / overall_total if overall_total else 0.0,
        },
    }


def format_report(report: Dict) -> str:
    """Render the stratified report as readable text."""
    lines = ["Accuracy by document type and field (stratified):", ""]
    for dtype, bucket in sorted(report["by_type"].items()):
        lines.append(f"  {dtype}: {bucket['accuracy']:.0%} ({bucket['correct']}/{bucket['total']})")
        for field, fstat in sorted(bucket["fields"].items()):
            lines.append(
                f"      - {field}: {fstat['accuracy']:.0%} ({fstat['correct']}/{fstat['total']})"
            )
    ov = report["overall"]
    lines += ["", f"  OVERALL (do not read in isolation): {ov['accuracy']:.0%} "
              f"({ov['correct']}/{ov['total']})"]
    return "\n".join(lines)
