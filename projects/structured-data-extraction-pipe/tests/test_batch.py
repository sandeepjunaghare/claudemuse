"""Phase 4: Batch reconciliation by custom_id + failure recovery (TR7). Mocked — no network."""

from types import SimpleNamespace as NS

import batch
from batch import BatchDoc, BatchReconciliation


def _succeeded(cid, name, inp):
    message = NS(content=[NS(type="tool_use", name=name, input=inp)], stop_reason="tool_use")
    return NS(custom_id=cid, result=NS(type="succeeded", message=message))


def _failed(cid, rtype):
    return NS(custom_id=cid, result=NS(type=rtype))


def test_reconcile_keys_by_custom_id_and_is_order_insensitive():
    # Deliberately out of order — results arrive in any order (TR7).
    results = [
        _failed("d3", "expired"),
        _succeeded("d1", "extract_invoice", {"vendor": "Acme", "stated_total": 80.0}),
        _failed("d2", "errored"),
        _succeeded("d4", "extract_paper", {"title": "X"}),
    ]
    rec = batch.reconcile(results)
    assert set(rec.succeeded) == {"d1", "d4"}
    assert rec.succeeded["d1"]["doc_type"] == "invoice"
    assert rec.succeeded["d1"]["raw"]["vendor"] == "Acme"
    assert set(rec.failed) == {"d2", "d3"}
    assert set(rec.failed_ids) == {"d2", "d3"}


def test_succeeded_without_tool_use_counts_as_failed():
    message = NS(content=[NS(type="text", text="no tool call")], stop_reason="end_turn")
    result = NS(custom_id="d1", result=NS(type="succeeded", message=message))
    rec = batch.reconcile([result])
    assert "d1" in rec.failed


def test_build_request_shape():
    req = batch.build_request(BatchDoc("d1", "INVOICE ...", doc_type="invoice"))
    assert req["custom_id"] == "d1"
    params = req["params"]
    assert params["model"] and params["system"] and params["messages"]
    assert params["tool_choice"] == {"type": "tool", "name": "extract_invoice"}


def test_chunk_document():
    assert batch.chunk_document("short") == ["short"]
    big = "\n\n".join(["paragraph " * 500 for _ in range(10)])
    chunks = batch.chunk_document(big, max_chars=4000)
    assert len(chunks) > 1
    assert all(len(c) <= 4000 or "\n\n" not in c for c in chunks)


def test_resubmit_only_failed_docs():
    docs = [BatchDoc("d1", "a"), BatchDoc("d2", "b"), BatchDoc("d3", "c")]
    rec = BatchReconciliation(succeeded={"d1": {}, "d3": {}}, failed={"d2": "errored"})

    class FakeBatches:
        def __init__(self):
            self.created = None

        def create(self, requests):
            self.created = requests
            return NS(id="batch_resubmit")

    fake_client = NS(messages=NS(batches=FakeBatches()))
    new_id, resubmitted = batch.resubmit_failed(docs, rec, client=fake_client)

    assert new_id == "batch_resubmit"
    assert [d.custom_id for d in resubmitted] == ["d2"]  # ONLY the failure
    assert len(fake_client.messages.batches.created) == 1


def test_resubmit_noop_when_no_failures():
    docs = [BatchDoc("d1", "a")]
    rec = BatchReconciliation(succeeded={"d1": {}}, failed={})
    assert batch.resubmit_failed(docs, rec) == (None, [])
