"""Summarize ingested user records.

SEEDED FIXTURE INTENT: the CONSUMER half of the cross-file data-flow bug. It
reads ``rec["userId"]`` while ``ingest.to_record`` writes ``"user_id"`` — the key
mismatch raises ``KeyError`` at runtime. In ISOLATION this file looks fine (it
just reads a key that plausibly exists); the defect only appears when reasoning
across ``ingest.py`` and this file together. Single-file review is EXPECTED to
miss it. Ground-truth case: ``cross-file-key-mismatch`` (requires_integration_pass=true).
"""


def user_ids(records):
    """Extract the user id from each ingested record."""
    return [rec["userId"] for rec in records]


def summarize(records):
    """Return a count + the list of user ids present in ``records``."""
    ids = user_ids(records)
    return {"count": len(ids), "ids": ids}
