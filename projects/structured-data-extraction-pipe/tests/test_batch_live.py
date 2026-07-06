"""Live integration: a >=100-doc Batch API run with seeded failures resubmitted by custom_id.

Run with:  ../../.venv/bin/python -m pytest -m integration -k batch_live
Skipped automatically when no key is present. This SPENDS TOKENS and can take up to the
Batch API's 24h window (usually well under an hour). It is not part of the offline gate.

Acceptance criterion: a batch of >=100 docs runs via the Batch API; the ~3 seeded failures
are resubmitted by `custom_id` (not the whole batch).
"""

import itertools

import pytest

import batch
import config
from batch import BatchDoc
from data.corpus import LABELED

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not config.anthropic_key_present(), reason="No ANTHROPIC_API_KEY for live batch."),
]

_SEED_FAILURE_INDICES = {10, 50, 90}
_INVALID_MODEL = "claude-does-not-exist-0"  # forces an errored result for seeded docs


def _hundred_docs():
    """100 BatchDocs cycled from the labeled set, keyed by custom_id doc-000..doc-099."""
    cycle = itertools.cycle(LABELED)
    docs = []
    for i in range(100):
        src = next(cycle)
        docs.append(BatchDoc(custom_id=f"doc-{i:03d}", document=src.document, doc_type=src.doc_type))
    return docs


def test_batch_run_with_seeded_failures_resubmitted():
    client = config.get_client()
    docs = _hundred_docs()
    seeded_ids = {f"doc-{i:03d}" for i in _SEED_FAILURE_INDICES}

    # Build requests; corrupt the seeded ones with an invalid model so they error.
    requests = []
    for i, doc in enumerate(docs):
        req = batch.build_request(doc)
        if i in _SEED_FAILURE_INDICES:
            req["params"]["model"] = _INVALID_MODEL
        requests.append(req)
    assert len(requests) >= 100

    created = client.messages.batches.create(requests=requests)
    batch.wait_for_batch(created.id, client=client)
    rec = batch.collect_batch(created.id, client=client)

    # The seeded failures are detected by custom_id; the rest succeeded.
    assert seeded_ids <= set(rec.failed_ids)
    assert len(rec.succeeded) >= 100 - len(seeded_ids) - 5  # allow a few incidental errors

    # Resubmit ONLY the failed docs (original, valid model) — not the whole batch.
    new_id, resubmitted = batch.resubmit_failed(docs, rec, client=client)
    assert new_id is not None
    assert seeded_ids <= {d.custom_id for d in resubmitted}

    batch.wait_for_batch(new_id, client=client)
    rec2 = batch.collect_batch(new_id, client=client)
    assert seeded_ids <= set(rec2.succeeded)  # recovered on resubmission
