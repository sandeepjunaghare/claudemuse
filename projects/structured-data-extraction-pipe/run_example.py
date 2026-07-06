"""Minimal one-shot example: extract one document end-to-end and print the result.

Hits the live Anthropic API (extraction), so it needs `ANTHROPIC_API_KEY` in the
workspace-root `.env`. Run from the project root with the shared venv:

    ../../.venv/bin/python run_example.py
"""

import json
import sys

sys.path.insert(0, "src")

import config
from data.corpus import SAMPLES
from pipeline import extract_document

config.load_env()


def main():
    if not config.anthropic_key_present():
        print("No ANTHROPIC_API_KEY found in the workspace .env — cannot run the live example.")
        return

    # The seeded bad-sum invoice: expect conflict_detected=True and route=human_review.
    document = SAMPLES["bad_sum_invoice"]
    result = extract_document(document)

    print("DOC TYPE:   ", result.doc_type)
    print("VALID:      ", result.valid)
    print("CONFLICT:   ", result.conflict_detected)
    print("ROUTE:      ", result.route)
    print("FAILURE:    ", result.failure)
    print("CONFIDENCE: ", result.confidence)
    print("DATA:")
    print(json.dumps(result.data, indent=2, default=str))


if __name__ == "__main__":
    main()
