"""Ingest raw users into record dicts.

SEEDED FIXTURE INTENT: the PRODUCER half of a cross-file data-flow bug. This file
writes the key ``"user_id"``; ``summary.py`` later reads ``"userId"`` — a key
mismatch that raises ``KeyError`` at runtime. In ISOLATION this file looks
perfectly fine; only cross-file reasoning reveals the defect. A single-file
review is EXPECTED to miss it (Phase-2 gap); the Phase-3 integration pass catches
it. Ground-truth case: ``cross-file-key-mismatch`` (requires_integration_pass=true).
Deliberately NO comment hinting at the consumer's spelling.
"""


def to_record(user):
    """Flatten a user object into a serializable record dict."""
    return {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
    }


def ingest(users):
    """Turn an iterable of users into a list of record dicts."""
    return [to_record(u) for u in users]
