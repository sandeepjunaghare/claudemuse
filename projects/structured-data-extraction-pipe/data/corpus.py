"""Labeled validation set — ground truth for calibration and the regression gate.

13 synthetic documents (no secrets, no PII), segmented by type, seeded so that every
behavior the acceptance criteria demand is reproducible:
- a clean invoice whose totals match (must NOT be flagged),
- a bad-sum invoice (must be flagged via calculated != stated),
- an invoice missing its PO number (must return null, not a fabricated value),
- a novel contract category (must land in "other" + detail),
- a paper whose authors are "Smith et al." (must fail fast — missing info),
- a comma-in-number invoice (a likely format error, fixed on retry-with-feedback),
- varied layouts (inline citations vs bibliography; narrative vs table invoice).

`expected` holds only the fields we assert on (a ground-truth subset). Values are compared
structurally by `audit.py`, never against the model's wording.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class LabeledDoc:
    id: str
    doc_type: str
    document: str
    expected: dict
    tags: Tuple[str, ...] = field(default_factory=tuple)


LABELED: List[LabeledDoc] = [
    # --- Invoices ------------------------------------------------------------
    LabeledDoc(
        id="inv-clean",
        doc_type="invoice",
        document=(
            "INVOICE 1042  Vendor: Acme Corp  Date: 2026-02-10  PO: PO-8891\n"
            "2 x Widget @ 25.00 = 50.00\n"
            "1 x Gadget @ 30.00 = 30.00\n"
            "Total: $80.00 USD"
        ),
        expected={"vendor": "Acme Corp", "po_number": "PO-8891", "stated_total": 80.0,
                  "calculated_total": 80.0, "currency": "USD"},
        tags=("clean",),
    ),
    LabeledDoc(
        id="inv-badsum",
        doc_type="invoice",
        document=(
            "INVOICE 1043  Vendor: Globex  Date: March 3, 2026  PO: PO-5501\n"
            "4 x Cable @ 120.00 = 480.00\n"
            "1 x Router @ 500.00 = 500.00\n"
            "Total: $1,080.00 USD"
        ),
        # Line items sum to 980 but the page states 1080 — arithmetic conflict.
        expected={"vendor": "Globex", "stated_total": 1080.0, "calculated_total": 980.0},
        tags=("conflict",),
    ),
    LabeledDoc(
        id="inv-nopo",
        doc_type="invoice",
        document=(
            "INVOICE 1044  Vendor: Initech  Date: 2026-01-05\n"
            "3 x License @ 100.00 = 300.00\n"
            "Total: $300.00 USD"
        ),
        # No PO on the document — must be null, never fabricated.
        expected={"vendor": "Initech", "po_number": None, "stated_total": 300.0,
                  "calculated_total": 300.0},
        tags=("absent_field",),
    ),
    LabeledDoc(
        id="inv-narrative",
        doc_type="invoice",
        document=(
            "Hi — this is the bill from Umbrella Ltd for the January work. We provided "
            "ten hours of consulting at ninety dollars an hour, for a total of nine "
            "hundred dollars. Invoice date is 2026-01-31."
        ),
        expected={"vendor": "Umbrella Ltd", "stated_total": 900.0, "currency": "USD"},
        tags=("narrative", "layout"),
    ),
    LabeledDoc(
        id="inv-commanum",
        doc_type="invoice",
        document=(
            "INVOICE 1050  Vendor: Stark Industries  Date: 12/25/2026\n"
            "1 x Reactor @ 12,500.00 = 12,500.00\n"
            "Total: $12,500.00 USD"
        ),
        # Comma-formatted numbers — the model must normalize; a likely format-error case.
        expected={"vendor": "Stark Industries", "stated_total": 12500.0,
                  "calculated_total": 12500.0, "invoice_date": "2026-12-25"},
        tags=("format_error", "normalization"),
    ),
    # --- Contracts -----------------------------------------------------------
    LabeledDoc(
        id="con-nda",
        doc_type="contract",
        document=(
            "MUTUAL NON-DISCLOSURE AGREEMENT between Alpha LLC and Beta Inc, effective "
            "January 15, 2026, for a term of two years."
        ),
        expected={"category": "nda", "effective_date": "2026-01-15",
                  "parties": ["Alpha LLC", "Beta Inc"]},
        tags=("known_category",),
    ),
    LabeledDoc(
        id="con-novel",
        doc_type="contract",
        document=(
            "DATA PROCESSING ADDENDUM between Cloud Co and Client Co, effective "
            "2026-04-01. Governs processing of personal data under GDPR."
        ),
        # "Data Processing Addendum" is not in the enum — must be other + detail.
        expected={"category": "other", "effective_date": "2026-04-01"},
        tags=("novel_category",),
    ),
    LabeledDoc(
        id="con-lease",
        doc_type="contract",
        document=(
            "COMMERCIAL LEASE between Landlord Realty and Tenant Corp, commencing "
            "Feb 1 2026, term 36 months."
        ),
        expected={"category": "lease", "effective_date": "2026-02-01"},
        tags=("known_category",),
    ),
    LabeledDoc(
        id="con-employment",
        doc_type="contract",
        document=(
            "EMPLOYMENT AGREEMENT between Widgets Inc and Jane Roe, start date "
            "2026-03-16, at-will."
        ),
        expected={"category": "employment", "effective_date": "2026-03-16"},
        tags=("known_category",),
    ),
    # --- Papers --------------------------------------------------------------
    LabeledDoc(
        id="paper-inline",
        doc_type="paper",
        document=(
            "Efficient Attention at Scale\nBy L. Zhang and M. Ito.\n"
            "We extend sparse attention (Child et al., 2019) with adaptive spans (Sukhbaatar, 2019)."
        ),
        expected={"title": "Efficient Attention at Scale", "authors": ["L. Zhang", "M. Ito"]},
        tags=("inline_citation", "layout"),
    ),
    LabeledDoc(
        id="paper-biblio",
        doc_type="paper",
        document=(
            "Foundations of Federated Learning\nAuthor: P. Novak\n"
            "References:\n[1] McMahan et al., 2017.\n[2] Konecny, 2016."
        ),
        expected={"title": "Foundations of Federated Learning", "authors": ["P. Novak"]},
        tags=("bibliography", "layout"),
    ),
    LabeledDoc(
        id="paper-etal",
        doc_type="paper",
        document=(
            "Scaling Laws Revisited\nBy Smith et al. (full author list in the supplementary "
            "material, not included here).\nAbstract: We revisit scaling laws."
        ),
        # The author list is genuinely absent ("et al." + in a doc not provided) — fail fast.
        expected={"title": "Scaling Laws Revisited"},
        tags=("missing_info",),
    ),
    LabeledDoc(
        id="paper-noauthors",
        doc_type="paper",
        document=(
            "Notes on Compiler Design\n(no byline)\nThis internal memo covers register "
            "allocation and instruction scheduling."
        ),
        expected={"title": "Notes on Compiler Design", "authors": []},
        tags=("absent_field",),
    ),
]

#: Edge-case documents keyed by the behavior they trigger (seeded samples — TR/FR demos).
SAMPLES: Dict[str, str] = {name: doc.document for name, doc in {
    "bad_sum_invoice": LABELED[1],
    "absent_field_invoice": LABELED[2],
    "novel_category_contract": LABELED[6],
    "format_error_invoice": LABELED[4],
    "missing_info_paper": LABELED[11],
}.items()}


def by_tag(tag: str) -> List[LabeledDoc]:
    """All labeled docs carrying a given tag."""
    return [d for d in LABELED if tag in d.tags]
