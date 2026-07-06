"""Extraction prompt: normalization rules + the never-fabricate contract (TR3/FR2).

Normalization lives here, in the prompt, alongside the strict schema — this is what
stops valid-but-inconsistent values (a date the schema accepts but that's formatted
three different ways across documents). The never-fabricate and enum-other rules
enforce FR2/TR2 at the point of generation.
"""

from typing import List, Optional

SYSTEM_PROMPT = """\
You extract structured data from documents by calling the provided extraction tool.
The tool's schema is the contract; follow it exactly. Beyond valid JSON, obey these rules.

NEVER FABRICATE (this is the cardinal rule):
- If a field is genuinely absent from the document, return null (or an empty list for
  list fields). Do NOT invent a plausible-looking value to fill a field.
- Missing information is a fact to report, not a gap to fill.

EXTENSIBLE CATEGORIES:
- For a categorical field, if the document's category is not one of the known enum
  values, use "other" and put the specific label in the matching *_detail field.
- If the category is genuinely ambiguous, use "unclear".

NORMALIZATION (apply consistently so values are comparable across documents):
- Dates -> ISO 8601 "YYYY-MM-DD" (e.g. "Jan 3, 2026" -> "2026-01-03"). If only a month
  and year are given, use the first day. If a date is absent, return null.
- Money -> a numeric amount plus an ISO-4217 currency string. Parse free text:
  "five bucks" -> amount 5.0, currency "USD"; "$1,080.50" -> 1080.5. Strip symbols and
  thousands separators. Put the currency once in the `currency` field.
- Quantities / fractions expressed in words -> numbers: "half" -> 0.5, "a dozen" -> 12,
  "one and a half" -> 1.5.

SELF-CORRECTION (invoices):
- Populate `calculated_total` by summing the line-item amounts yourself.
- Populate `stated_total` with the total printed on the document, verbatim (normalized to
  a number). Report both even when they disagree — do not "fix" one to match the other.

CONFIDENCE:
- Populate `field_confidence` with a number in [0, 1] for each top-level field you filled,
  keyed by the field name. Lower it when the source is ambiguous, degraded, or inferred.
"""


def build_user_content(document: str, feedback: Optional[str] = None) -> str:
    """Assemble the user turn: the document, plus targeted retry feedback when present (TR4).

    On a retry, `feedback` carries the original document, the failed extraction, and the
    *specific* validation error — the three things the model needs to fix a format error.
    """
    if feedback is None:
        return f"Extract the structured data from this document:\n\n{document}"
    return (
        "Your previous extraction failed validation. Fix ONLY the specific problem below; "
        "do not change correct fields, and do not fabricate values for information the "
        "document does not contain.\n\n"
        f"{feedback}\n\n"
        f"Document:\n\n{document}"
    )


def build_messages(
    document: str,
    feedback: Optional[str] = None,
    example_messages: Optional[List[dict]] = None,
) -> List[dict]:
    """Full message list: few-shot layout examples (TR6) followed by the real document."""
    messages: List[dict] = list(example_messages or [])
    messages.append({"role": "user", "content": build_user_content(document, feedback)})
    return messages
