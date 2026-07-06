"""Few-shot layout examples (TR6).

Unfamiliar layouts are where extraction silently returns null/empty — a bibliography
looks nothing like inline citations; a narrative invoice looks nothing like a table.
These 2–4 examples span those structures so the model generalizes across layout instead
of over-fitting the first shape it sees.

Each example is a (user document -> assistant tool_use -> user tool_result) triple, the
canonical shape for teaching a tool call. The tool names used here (`extract_paper`,
`extract_invoice`) must appear in the request's `tools` list — `extract.extract_once`
always passes the full tool registry, so they always resolve.
"""

from typing import List


def _turn(example_id: str, document: str, tool_name: str, tool_input: dict) -> List[dict]:
    """One few-shot triple."""
    return [
        {"role": "user", "content": f"Extract the structured data from this document:\n\n{document}"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": example_id, "name": tool_name, "input": tool_input}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": example_id, "content": "Recorded."}],
        },
    ]


def example_messages() -> List[dict]:
    """The few-shot bank: inline-citation paper, bibliography paper, and a table invoice."""
    messages: List[dict] = []

    # Inline-citation layout — authors appear in a byline, references cited inline as (Author, Year).
    messages += _turn(
        "toolu_fewshot_paper_inline",
        (
            "Deep Retrieval for Long Documents\n"
            "By A. Okafor and R. Mehta.\n"
            "We build on dense retrieval (Karpukhin et al., 2020) and extend it with "
            "hierarchical chunking (Liu, 2021). Section 1 introduces the problem; Section 2 "
            "reviews related work."
        ),
        "extract_paper",
        {
            "title": "Deep Retrieval for Long Documents",
            "authors": ["A. Okafor", "R. Mehta"],
            "references": ["Karpukhin et al., 2020", "Liu, 2021"],
            "sections": ["Introduction", "Related Work"],
            "field_confidence": {"title": 0.98, "authors": 0.95, "references": 0.9},
        },
    )

    # Bibliography layout — references in a numbered list at the end, no inline cites.
    messages += _turn(
        "toolu_fewshot_paper_biblio",
        (
            "A Survey of Graph Neural Networks\n"
            "Author: J. Fernandez\n"
            "Abstract: We survey GNN architectures.\n"
            "References:\n"
            "[1] Kipf & Welling, Semi-Supervised Classification, 2017.\n"
            "[2] Velickovic et al., Graph Attention Networks, 2018."
        ),
        "extract_paper",
        {
            "title": "A Survey of Graph Neural Networks",
            "authors": ["J. Fernandez"],
            "abstract": "We survey GNN architectures.",
            "references": [
                "Kipf & Welling, Semi-Supervised Classification, 2017.",
                "Velickovic et al., Graph Attention Networks, 2018.",
            ],
            "field_confidence": {"title": 0.97, "authors": 0.96, "references": 0.92},
        },
    )

    # Tabular invoice — line items in a table, totals at the bottom.
    messages += _turn(
        "toolu_fewshot_invoice_table",
        (
            "INVOICE  Vendor: Bluebird Supplies  Date: 03/01/2026  PO: PO-77\n"
            "Qty  Item            Unit    Amount\n"
            "2    Ream paper      6.00    12.00\n"
            "1    Toner           48.00   48.00\n"
            "Total: $60.00  (USD)"
        ),
        "extract_invoice",
        {
            "vendor": "Bluebird Supplies",
            "invoice_date": "2026-03-01",
            "po_number": "PO-77",
            "currency": "USD",
            "line_items": [
                {"description": "Ream paper", "quantity": 2, "unit_price": 6.0, "amount": 12.0},
                {"description": "Toner", "quantity": 1, "unit_price": 48.0, "amount": 48.0},
            ],
            "stated_total": 60.0,
            "calculated_total": 60.0,
            "field_confidence": {"vendor": 0.98, "stated_total": 0.99, "line_items": 0.95},
        },
    )

    return messages
